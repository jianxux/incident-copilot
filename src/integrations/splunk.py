"""Splunk integration adapter for log retrieval."""

import asyncio
import base64
from datetime import UTC, datetime

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings
from ..models import LogEntry

logger = structlog.get_logger()


class SplunkAdapter:
    """Adapter for Splunk REST API.

    Supports both Splunk Enterprise and Splunk Cloud.
    Uses the Search REST API for log queries.
    """

    def __init__(self, settings: Settings, verify_ssl: bool = True):
        self.settings = settings
        self.base_url = settings.splunk_url.rstrip("/") if settings.splunk_url else ""
        self.token = settings.splunk_token
        self.username = settings.splunk_username
        self.password = settings.splunk_password
        self.index_map = settings.splunk_index_map
        self.verify_ssl = verify_ssl  # Configurable for internal Splunk deployments

    def _get_headers(self) -> dict:
        """Get auth headers for Splunk API."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        if self.token:
            # Token-based auth (recommended for automation)
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.username and self.password:
            # Basic auth fallback
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"

        return headers

    def _get_index_for_service(self, service_name: str) -> str | None:
        """Map service name to Splunk index."""
        if service_name in self.index_map:
            return self.index_map[service_name]

        # Try variations
        normalized = service_name.lower().replace("-", "_")
        for key, value in self.index_map.items():
            if key.lower().replace("-", "_") == normalized:
                return value

        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _create_search_job(
        self,
        search_query: str,
        earliest_time: str = "-1h",
        latest_time: str = "now",
    ) -> str:
        """Create an async search job and return the job SID."""
        async with httpx.AsyncClient(timeout=60.0, verify=self.verify_ssl) as client:  # nosec B501 - SSL verification intentionally configurable for internal Splunk deployments
            response = await client.post(
                f"{self.base_url}/services/search/jobs",
                headers=self._get_headers(),
                data={
                    "search": search_query,
                    "earliest_time": earliest_time,
                    "latest_time": latest_time,
                    "output_mode": "json",
                    "exec_mode": "normal",
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("sid", "")

    async def _wait_for_job(
        self,
        sid: str,
        timeout_seconds: int = 60,
        poll_interval: float = 1.0,
    ) -> bool:
        """Wait for a search job to complete."""
        start_time = datetime.now()

        async with httpx.AsyncClient(timeout=30.0, verify=self.verify_ssl) as client:  # nosec B501 - SSL verification intentionally configurable for internal Splunk deployments
            while (datetime.now() - start_time).seconds < timeout_seconds:
                response = await client.get(
                    f"{self.base_url}/services/search/jobs/{sid}",
                    headers=self._get_headers(),
                    params={"output_mode": "json"},
                )
                response.raise_for_status()

                result = response.json()
                entry = result.get("entry", [{}])[0]
                content = entry.get("content", {})

                if content.get("isDone"):
                    return True
                if content.get("isFailed"):
                    logger.error("Splunk search job failed", sid=sid)
                    return False

                await asyncio.sleep(poll_interval)

        logger.warning("Splunk search job timed out", sid=sid)
        return False

    async def _get_job_results(
        self,
        sid: str,
        count: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Get results from a completed search job."""
        async with httpx.AsyncClient(timeout=30.0, verify=self.verify_ssl) as client:  # nosec B501 - SSL verification intentionally configurable for internal Splunk deployments
            response = await client.get(
                f"{self.base_url}/services/search/jobs/{sid}/results",
                headers=self._get_headers(),
                params={
                    "output_mode": "json",
                    "count": count,
                    "offset": offset,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("results", [])

    async def fetch_logs(
        self,
        service_name: str,
        minutes_back: int = 60,
        max_results: int = 100,
        severity: str | None = None,
    ) -> list[LogEntry]:
        """Fetch logs for a service from Splunk.

        Args:
            service_name: Name of the service to fetch logs for
            minutes_back: How many minutes of logs to fetch
            max_results: Maximum number of log entries to return
            severity: Optional severity filter (ERROR, WARN, INFO, DEBUG)

        Returns:
            List of LogEntry objects
        """
        if not self.base_url:
            logger.warning("Splunk URL not configured")
            return []

        index = self._get_index_for_service(service_name)
        if not index:
            logger.warning(
                "No Splunk index mapping found for service",
                service=service_name,
            )
            # Try to use a default or the service name as index
            index = service_name.lower().replace("-", "_")

        # Build SPL query
        query_parts = [f'search index="{index}"']

        # Add service filter
        query_parts.append(f'(service="{service_name}" OR app="{service_name}")')

        # Add severity filter
        if severity:
            if severity.upper() == "ERROR":
                query_parts.append(
                    '(level="ERROR" OR level="FATAL" OR severity="error" OR severity="fatal")'
                )
            elif severity.upper() == "WARN":
                query_parts.append(
                    '(level="WARN" OR level="WARNING" OR severity="warn" OR severity="warning")'
                )

        # Sort by time descending
        query_parts.append("| sort -_time")
        query_parts.append(f"| head {max_results}")

        search_query = " ".join(query_parts)

        # Calculate time range
        earliest_time = f"-{minutes_back}m"

        try:
            logger.info(
                "Creating Splunk search job",
                service=service_name,
                index=index,
                minutes_back=minutes_back,
            )

            # Create search job
            sid = await self._create_search_job(
                search_query=search_query,
                earliest_time=earliest_time,
                latest_time="now",
            )

            if not sid:
                logger.error("Failed to create Splunk search job")
                return []

            # Wait for completion
            completed = await self._wait_for_job(sid, timeout_seconds=60)
            if not completed:
                return []

            # Get results
            raw_results = await self._get_job_results(sid, count=max_results)

            # Convert to LogEntry objects
            entries = []
            for result in raw_results:
                timestamp = self._parse_timestamp(result.get("_time", ""))
                entries.append(
                    LogEntry(
                        timestamp=timestamp or datetime.now(UTC),
                        message=result.get("_raw", result.get("message", "")),
                        level=result.get("level", result.get("severity", "INFO")).upper(),
                        service=service_name,
                        metadata={
                            "host": result.get("host", ""),
                            "source": result.get("source", ""),
                            "sourcetype": result.get("sourcetype", ""),
                            "index": index,
                            **{
                                k: v
                                for k, v in result.items()
                                if k
                                not in (
                                    "_time",
                                    "_raw",
                                    "message",
                                    "level",
                                    "severity",
                                    "host",
                                    "source",
                                    "sourcetype",
                                )
                            },
                        },
                    )
                )

            logger.info(
                "Fetched logs from Splunk",
                service=service_name,
                count=len(entries),
            )

            return entries

        except httpx.HTTPStatusError as e:
            logger.error(
                "Splunk API error",
                status_code=e.response.status_code,
                detail=e.response.text,
            )
            return []
        except Exception as e:
            logger.error("Error fetching Splunk logs", error=str(e))
            return []

    def _parse_timestamp(self, time_str: str) -> datetime | None:
        """Parse Splunk timestamp to datetime."""
        if not time_str:
            return None

        # Splunk uses ISO format with timezone
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S.%f %z",
            "%Y-%m-%d %H:%M:%S %z",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue

        # Try parsing as epoch
        try:
            return datetime.fromtimestamp(float(time_str), tz=UTC)
        except (ValueError, TypeError):
            pass

        return None

    async def run_saved_search(
        self,
        saved_search_name: str,
        earliest_time: str | None = None,
        latest_time: str | None = None,
    ) -> list[dict]:
        """Run a saved/scheduled search by name.

        Args:
            saved_search_name: Name of the saved search
            earliest_time: Override earliest time (optional)
            latest_time: Override latest time (optional)

        Returns:
            List of result dictionaries
        """
        if not self.base_url:
            return []

        try:
            async with httpx.AsyncClient(timeout=60.0, verify=self.verify_ssl) as client:  # nosec B501 - SSL verification intentionally configurable for internal Splunk deployments
                # Dispatch the saved search
                dispatch_params = {}
                if earliest_time:
                    dispatch_params["dispatch.earliest_time"] = earliest_time
                if latest_time:
                    dispatch_params["dispatch.latest_time"] = latest_time

                response = await client.post(
                    f"{self.base_url}/services/saved/searches/{saved_search_name}/dispatch",
                    headers=self._get_headers(),
                    data=dispatch_params,
                )
                response.raise_for_status()
                result = response.json()
                sid = result.get("sid", "")

                if not sid:
                    return []

                # Wait and get results
                completed = await self._wait_for_job(sid)
                if not completed:
                    return []

                return await self._get_job_results(sid)

        except Exception as e:
            logger.error(
                "Error running Splunk saved search",
                search=saved_search_name,
                error=str(e),
            )
            return []

    async def get_health(self) -> dict:
        """Check Splunk connection health."""
        if not self.base_url:
            return {"status": "unconfigured"}

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl) as client:  # nosec B501 - SSL verification intentionally configurable for internal Splunk deployments
                response = await client.get(
                    f"{self.base_url}/services/server/info",
                    headers=self._get_headers(),
                    params={"output_mode": "json"},
                )
                response.raise_for_status()
                result = response.json()

                entry = result.get("entry", [{}])[0]
                content = entry.get("content", {})

                return {
                    "status": "healthy",
                    "version": content.get("version", "unknown"),
                    "server_name": content.get("serverName", "unknown"),
                    "os": content.get("os_name", "unknown"),
                }

        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def search_alerts(
        self,
        service_name: str,
        minutes_back: int = 60,
    ) -> list[dict]:
        """Search for triggered alerts related to a service.

        Args:
            service_name: Service name to search for
            minutes_back: How far back to search

        Returns:
            List of triggered alerts
        """
        if not self.base_url:
            return []

        try:
            # Query triggered alerts
            search_query = f"""
            search index=_audit action=alert_fired
            | search ss_name="*{service_name}*" OR search="*{service_name}*"
            | sort -_time
            | head 10
            """

            sid = await self._create_search_job(
                search_query=search_query,
                earliest_time=f"-{minutes_back}m",
                latest_time="now",
            )

            if not sid:
                return []

            completed = await self._wait_for_job(sid)
            if not completed:
                return []

            return await self._get_job_results(sid)

        except Exception as e:
            logger.error("Error searching Splunk alerts", error=str(e))
            return []
