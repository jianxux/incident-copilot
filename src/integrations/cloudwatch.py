"""AWS CloudWatch Logs integration adapter."""

from datetime import datetime, timedelta
from typing import Any

import structlog

from ..config import Settings
from ..models import DatadogContext, LogEntry, LogSummary, MetricSnapshot

logger = structlog.get_logger()


class CloudWatchAdapter:
    """Adapter for AWS CloudWatch Logs API.
    
    Provides log fetching capabilities parallel to DatadogAdapter,
    using the same output format for seamless integration.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        self._logs_client = None

    def _get_logs_client(self):
        """Lazily initialize CloudWatch Logs client."""
        if self._logs_client is None:
            try:
                import boto3
            except ImportError:
                raise ImportError(
                    "boto3 is required for CloudWatch integration. "
                    "Install with: pip install boto3"
                )

            # Build client kwargs
            client_kwargs: dict[str, Any] = {
                "service_name": "logs",
            }

            if self.settings.aws_region:
                client_kwargs["region_name"] = self.settings.aws_region

            # Use explicit credentials if provided, otherwise fall back to boto3 defaults
            # (env vars, IAM role, ~/.aws/credentials, etc.)
            if self.settings.aws_access_key_id and self.settings.aws_secret_access_key:
                client_kwargs["aws_access_key_id"] = self.settings.aws_access_key_id
                client_kwargs["aws_secret_access_key"] = self.settings.aws_secret_access_key

            self._logs_client = boto3.client(**client_kwargs)

        return self._logs_client

    def _get_log_groups_for_service(self, service_name: str) -> list[str]:
        """Get CloudWatch Log Group names for a service.
        
        Uses the log_group_mappings config, or falls back to convention-based naming.
        """
        # Check explicit mapping first
        if service_name in self.settings.cloudwatch_log_group_map:
            groups = self.settings.cloudwatch_log_group_map[service_name]
            # Handle both string and list values
            if isinstance(groups, str):
                return [g.strip() for g in groups.split(",")]
            return groups

        # Fall back to common naming conventions
        return [
            f"/aws/lambda/{service_name}",
            f"/ecs/{service_name}",
            f"/aws/ecs/{service_name}",
            f"/application/{service_name}",
        ]

    async def get_context(
        self, service_name: str, time_range_minutes: int = 15
    ) -> DatadogContext | None:
        """Get CloudWatch context (logs) for a service.
        
        Returns DatadogContext for compatibility with existing orchestrator.
        """
        if not self.settings.aws_region:
            logger.warning("cloudwatch_region_not_configured")
            return None

        try:
            logs = await self._fetch_logs(service_name, time_range_minutes)
            log_summaries = self._summarize_logs(logs)

            # Return as DatadogContext for compatibility
            return DatadogContext(
                service=service_name,
                logs=logs,
                log_summaries=log_summaries,
                metrics=MetricSnapshot(time_range_minutes=time_range_minutes),
            )

        except Exception as e:
            logger.error("cloudwatch_fetch_failed", service=service_name, error=str(e))
            return None

    async def _fetch_logs(
        self, service_name: str, time_range_minutes: int
    ) -> list[LogEntry]:
        """Fetch recent logs from CloudWatch Log Groups."""
        import asyncio

        client = self._get_logs_client()
        log_groups = self._get_log_groups_for_service(service_name)

        now = datetime.utcnow()
        start_time = now - timedelta(minutes=time_range_minutes)

        # Convert to milliseconds since epoch (CloudWatch uses ms)
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)

        all_logs: list[LogEntry] = []

        # Fetch from each log group
        for log_group in log_groups:
            try:
                logs = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda lg=log_group: self._fetch_logs_from_group(
                        client, lg, start_ms, end_ms, service_name
                    ),
                )
                all_logs.extend(logs)
            except client.exceptions.ResourceNotFoundException:
                logger.debug("cloudwatch_log_group_not_found", log_group=log_group)
                continue
            except Exception as e:
                logger.warning(
                    "cloudwatch_log_group_error",
                    log_group=log_group,
                    error=str(e),
                )
                continue

        # Sort by timestamp descending
        all_logs.sort(key=lambda x: x.timestamp, reverse=True)

        # Limit to 100 most recent
        return all_logs[:100]

    def _fetch_logs_from_group(
        self,
        client,
        log_group: str,
        start_ms: int,
        end_ms: int,
        service_name: str,
    ) -> list[LogEntry]:
        """Fetch logs from a single log group using filter_log_events."""
        logs: list[LogEntry] = []

        # Filter for error/warning patterns
        filter_pattern = '?ERROR ?WARN ?error ?warn ?Error ?Warning ?CRITICAL ?Exception'

        try:
            response = client.filter_log_events(
                logGroupName=log_group,
                startTime=start_ms,
                endTime=end_ms,
                filterPattern=filter_pattern,
                limit=50,  # Per log group limit
            )

            for event in response.get("events", []):
                timestamp = datetime.utcfromtimestamp(event["timestamp"] / 1000)
                message = event.get("message", "")

                # Infer log level from message
                level = self._infer_log_level(message)

                logs.append(
                    LogEntry(
                        timestamp=timestamp,
                        level=level,
                        message=message[:500],  # Truncate long messages
                        service=service_name,
                        host=event.get("logStreamName"),
                        attributes={
                            "log_group": log_group,
                            "event_id": event.get("eventId"),
                        },
                    )
                )

        except Exception as e:
            logger.warning(
                "cloudwatch_filter_error",
                log_group=log_group,
                error=str(e),
            )

        return logs

    def _infer_log_level(self, message: str) -> str:
        """Infer log level from message content."""
        message_lower = message.lower()

        if any(x in message_lower for x in ["critical", "fatal"]):
            return "critical"
        elif any(x in message_lower for x in ["error", "exception", "failed", "failure"]):
            return "error"
        elif any(x in message_lower for x in ["warn", "warning"]):
            return "warn"
        elif any(x in message_lower for x in ["info"]):
            return "info"
        else:
            return "unknown"

    async def run_insights_query(
        self,
        service_name: str,
        query: str,
        time_range_minutes: int = 15,
    ) -> list[dict]:
        """Run a CloudWatch Logs Insights query for structured searches.
        
        Args:
            service_name: Service name to determine log groups
            query: CloudWatch Logs Insights query string
            time_range_minutes: Time window to search
            
        Returns:
            List of query result records
        """
        import asyncio

        client = self._get_logs_client()
        log_groups = self._get_log_groups_for_service(service_name)

        # Filter to existing log groups only
        existing_groups = []
        for lg in log_groups:
            try:
                client.describe_log_groups(logGroupNamePrefix=lg, limit=1)
                existing_groups.append(lg)
            except Exception:
                continue

        if not existing_groups:
            logger.warning("no_valid_log_groups", service=service_name)
            return []

        now = datetime.utcnow()
        start_time = now - timedelta(minutes=time_range_minutes)

        start_ts = int(start_time.timestamp())
        end_ts = int(now.timestamp())

        try:
            # Start the query
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.start_query(
                    logGroupNames=existing_groups,
                    startTime=start_ts,
                    endTime=end_ts,
                    queryString=query,
                    limit=100,
                ),
            )

            query_id = response["queryId"]

            # Poll for results (max 30 seconds)
            max_wait = 30
            poll_interval = 0.5
            elapsed = 0

            while elapsed < max_wait:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.get_query_results(queryId=query_id),
                )

                status = result["status"]

                if status == "Complete":
                    # Parse results
                    records = []
                    for row in result.get("results", []):
                        record = {}
                        for field in row:
                            record[field["field"]] = field["value"]
                        records.append(record)
                    return records

                elif status in ["Failed", "Cancelled"]:
                    logger.error("insights_query_failed", status=status)
                    return []

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            logger.warning("insights_query_timeout", query_id=query_id)
            return []

        except Exception as e:
            logger.error("insights_query_error", error=str(e))
            return []

    def _summarize_logs(self, logs: list[LogEntry]) -> list[LogSummary]:
        """Create basic log summaries by grouping similar messages.
        
        Same logic as DatadogAdapter for consistency.
        """
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
