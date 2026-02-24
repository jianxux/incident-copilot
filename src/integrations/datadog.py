"""Datadog integration adapter."""

from datetime import datetime, timedelta, UTC

import httpx
import structlog

from ..config import Settings
from ..models import DatadogContext, LogEntry, LogSummary, MetricSnapshot

logger = structlog.get_logger()


class DatadogAdapter:
    """Adapter for Datadog API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.datadog_api_key
        self.app_key = settings.datadog_app_key
        self.site = settings.datadog_site

    @property
    def base_url(self) -> str:
        """Get base URL for Datadog API."""
        return f"https://api.{self.site}"

    def _get_headers(self) -> dict:
        """Get auth headers for Datadog API."""
        return {
            "DD-API-KEY": self.api_key,
            "DD-APPLICATION-KEY": self.app_key,
            "Content-Type": "application/json",
        }

    async def get_context(
        self, service_name: str, time_range_minutes: int = 15
    ) -> DatadogContext | None:
        """Get Datadog context (logs + metrics) for a service."""
        if not self.api_key or not self.app_key:
            # Datadog is optional; avoid warning spam per incident.
            logger.debug("datadog_credentials_not_configured")
            return None

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Fetch logs and metrics in parallel would be ideal
                # For simplicity, doing sequentially here
                logs = await self._fetch_logs(client, service_name, time_range_minutes)
                log_summaries = self._summarize_logs(logs)
                metrics = await self._fetch_metrics(
                    client, service_name, time_range_minutes
                )

                return DatadogContext(
                    service=service_name,
                    logs=logs,
                    log_summaries=log_summaries,
                    metrics=metrics,
                )

        except Exception as e:
            logger.error("datadog_fetch_failed", service=service_name, error=str(e))
            return None

    async def _fetch_logs(
        self, client: httpx.AsyncClient, service_name: str, time_range_minutes: int
    ) -> list[LogEntry]:
        """Fetch recent error/warning logs from Datadog."""
        now = datetime.now(UTC)
        start = now - timedelta(minutes=time_range_minutes)

        url = f"{self.base_url}/api/v2/logs/events/search"

        # Query for error/warning logs for this service
        query = f"service:{service_name} status:(error OR warn)"

        payload = {
            "filter": {
                "query": query,
                "from": start.isoformat() + "Z",
                "to": now.isoformat() + "Z",
            },
            "sort": "-timestamp",
            "page": {"limit": 100},
        }

        resp = await client.post(url, headers=self._get_headers(), json=payload)

        if resp.status_code != 200:
            logger.warning(
                "datadog_logs_failed", status=resp.status_code, body=resp.text[:200]
            )
            return []

        data = resp.json()
        logs = []

        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            try:
                timestamp = datetime.fromisoformat(
                    attrs.get("timestamp", "").replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                timestamp = datetime.now(UTC)

            logs.append(
                LogEntry(
                    timestamp=timestamp,
                    level=attrs.get("status", "unknown"),
                    message=attrs.get("message", "")[:500],  # Truncate long messages
                    service=attrs.get("service"),
                    host=attrs.get("host"),
                    attributes=attrs.get("attributes", {}),
                )
            )

        return logs

    def _summarize_logs(self, logs: list[LogEntry]) -> list[LogSummary]:
        """Create basic log summaries by grouping similar messages."""
        if not logs:
            return []

        # Simple grouping by first 100 chars of message
        groups: dict[str, list[LogEntry]] = {}

        for log in logs:
            # Create a simple pattern key
            key = log.message[:100] if log.message else "empty"
            if key not in groups:
                groups[key] = []
            groups[key].append(log)

        # Convert to summaries
        summaries = []
        for pattern, group_logs in sorted(groups.items(), key=lambda x: -len(x[1])):
            summaries.append(
                LogSummary(
                    pattern=pattern,
                    count=len(group_logs),
                    level=group_logs[0].level,
                    sample_message=group_logs[0].message,
                    first_seen=min(l.timestamp for l in group_logs),
                    last_seen=max(l.timestamp for l in group_logs),
                )
            )

        return summaries[:10]  # Top 10 patterns

    async def _fetch_metrics(
        self, client: httpx.AsyncClient, service_name: str, time_range_minutes: int
    ) -> MetricSnapshot | None:
        """Fetch key metrics from Datadog."""
        now = int(datetime.now(UTC).timestamp())
        start = now - (time_range_minutes * 60)

        url = f"{self.base_url}/api/v1/query"

        # Try to get error rate metric
        # This assumes standard APM metric naming - adjust as needed
        query = f"avg:trace.http.request.errors{{service:{service_name}}}.as_rate()"

        params = {"from": start, "to": now, "query": query}

        resp = await client.get(url, headers=self._get_headers(), params=params)

        if resp.status_code != 200:
            logger.warning("datadog_metrics_failed", status=resp.status_code)
            return MetricSnapshot(time_range_minutes=time_range_minutes)

        data = resp.json()
        series = data.get("series", [])

        error_rate = None
        if series and series[0].get("pointlist"):
            # Get the most recent point
            points = series[0]["pointlist"]
            if points:
                error_rate = points[-1][1]  # [timestamp, value]

        return MetricSnapshot(
            error_rate=error_rate,
            time_range_minutes=time_range_minutes,
        )
