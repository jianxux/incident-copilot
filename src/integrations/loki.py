"""Grafana Loki integration adapter.

Supports both self-hosted Loki and Grafana Cloud Loki.
Provides log fetching capabilities using LogQL queries.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from ..config import Settings
from ..models import DatadogContext, LogEntry, LogSummary, MetricSnapshot

logger = structlog.get_logger()


class LokiAdapter:
    """Adapter for Grafana Loki API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.loki_url.rstrip("/") if settings.loki_url else ""
        self.auth_type = settings.loki_auth_type
        self.org_id = settings.loki_org_id
        self.service_labels = settings.loki_service_labels

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers based on configured auth type."""
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if self.org_id:
            headers["X-Scope-OrgID"] = self.org_id

        if self.auth_type == "basic":
            import base64

            credentials = f"{self.settings.loki_username}:{self.settings.loki_password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        elif self.auth_type == "bearer":
            if self.settings.loki_token:
                headers["Authorization"] = f"Bearer {self.settings.loki_token}"

        return headers

    def _get_label_selector(self, service_name: str) -> str:
        """Get the Loki label selector for a service."""
        if service_name in self.service_labels:
            return self.service_labels[service_name]
        return f'{{service="{service_name}"}} or {{app="{service_name}"}}'

    def _build_logql_query(
        self, service_name: str, include_errors_only: bool = True
    ) -> str:
        """Build a LogQL query for fetching logs."""
        label_selector = self._get_label_selector(service_name)
        base_query = (
            label_selector
            if label_selector.startswith("{")
            else f"{{{label_selector}}}"
        )

        if include_errors_only:
            return f'{base_query} |~ "(?i)(error|warn|exception|failed|failure|critical|fatal)"'
        return base_query

    async def get_context(
        self, service_name: str, time_range_minutes: int = 15
    ) -> DatadogContext | None:
        """Get Loki context (logs) for a service."""
        if not self.base_url:
            logger.warning("loki_url_not_configured")
            return None

        try:
            logs = await self._fetch_logs(service_name, time_range_minutes)
            log_summaries = self._summarize_logs(logs)

            return DatadogContext(
                service=service_name,
                logs=logs,
                log_summaries=log_summaries,
                metrics=MetricSnapshot(time_range_minutes=time_range_minutes),
            )
        except Exception as e:
            logger.error("loki_fetch_failed", service=service_name, error=str(e))
            return None

    async def _fetch_logs(
        self, service_name: str, time_range_minutes: int, limit: int = 100
    ) -> list[LogEntry]:
        """Fetch logs from Loki using query_range endpoint."""
        now = datetime.now(UTC)
        start_time = now - timedelta(minutes=time_range_minutes)

        start_ns = int(start_time.timestamp() * 1e9)
        end_ns = int(now.timestamp() * 1e9)

        query = self._build_logql_query(service_name)
        all_logs: list[LogEntry] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self.base_url}/loki/api/v1/query_range"
            params: dict[str, Any] = {
                "query": query,
                "start": start_ns,
                "end": end_ns,
                "limit": min(limit, 1000),
                "direction": "backward",
            }

            try:
                resp = await client.get(
                    url, headers=self._get_auth_headers(), params=params
                )

                if resp.status_code != 200:
                    logger.warning("loki_query_failed", status=resp.status_code)
                    return []

                data = resp.json()
                result = data.get("data", {}).get("result", [])
                all_logs = self._parse_log_streams(result, service_name)

            except Exception as e:
                logger.error("loki_query_error", error=str(e))

        all_logs.sort(key=lambda x: x.timestamp, reverse=True)
        return all_logs[:limit]

    def _parse_log_streams(
        self, result: list[dict], service_name: str
    ) -> list[LogEntry]:
        """Parse Loki log streams into LogEntry objects."""
        logs: list[LogEntry] = []

        for stream in result:
            stream_labels = stream.get("stream", {})
            values = stream.get("values", [])

            for value in values:
                if len(value) < 2:
                    continue

                timestamp_ns, message = value[0], value[1]

                try:
                    timestamp = datetime.utcfromtimestamp(int(timestamp_ns) / 1e9)
                except (ValueError, TypeError):
                    timestamp = datetime.now(UTC)

                level = self._infer_log_level(message)
                host = stream_labels.get("pod") or stream_labels.get("host")

                logs.append(
                    LogEntry(
                        timestamp=timestamp,
                        level=level,
                        message=message[:500],
                        service=service_name,
                        host=host,
                        attributes={"labels": stream_labels, "source": "loki"},
                    )
                )

        return logs

    def _infer_log_level(self, message: str) -> str:
        """Infer log level from message content."""
        message_lower = message.lower()

        if any(x in message_lower for x in ["critical", "fatal", "panic"]):
            return "critical"
        elif any(
            x in message_lower for x in ["error", "exception", "failed", "failure"]
        ):
            return "error"
        elif any(x in message_lower for x in ["warn", "warning"]):
            return "warn"
        elif "info" in message_lower:
            return "info"
        else:
            return "unknown"

    def _summarize_logs(self, logs: list[LogEntry]) -> list[LogSummary]:
        """Create basic log summaries by grouping similar messages."""
        if not logs:
            return []

        groups: dict[str, list[LogEntry]] = {}
        for log in logs:
            key = log.message[:100] if log.message else "empty"
            if key not in groups:
                groups[key] = []
            groups[key].append(log)

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

        return summaries[:10]

    async def health_check(self) -> bool:
        """Check if Loki is reachable and healthy."""
        if not self.base_url:
            return False

        url = f"{self.base_url}/ready"

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(url, headers=self._get_auth_headers())
                return resp.status_code == 200
            except Exception:
                try:
                    url = f"{self.base_url}/loki/api/v1/labels"
                    resp = await client.get(url, headers=self._get_auth_headers())
                    return resp.status_code == 200
                except Exception:
                    return False
