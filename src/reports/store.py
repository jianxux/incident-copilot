"""In-memory store for scheduled reports."""

import asyncio
from datetime import UTC, datetime

from .models import ReportConfig, ReportOutput, ReportRunStatus, ReportStatus


class ReportStore:
    """
    Thread-safe in-memory store for report configurations and outputs.

    Designed to be replaced with a database backend later.
    """

    def __init__(self, max_outputs: int = 1000):
        self._configs: dict[str, ReportConfig] = {}
        self._outputs: dict[str, ReportOutput] = {}
        self._outputs_by_config: dict[str, list[str]] = {}
        self._max_outputs = max_outputs
        self._lock = asyncio.Lock()

    # --- Report Configuration Operations ---

    async def save_config(self, config: ReportConfig) -> ReportConfig:
        """Save or update a report configuration."""
        async with self._lock:
            config.updated_at = datetime.now(UTC)
            self._configs[config.id] = config
            if config.id not in self._outputs_by_config:
                self._outputs_by_config[config.id] = []
            return config

    async def get_config(self, config_id: str) -> ReportConfig | None:
        """Get a report configuration by ID."""
        return self._configs.get(config_id)

    async def get_all_configs(
        self,
        status: ReportStatus | None = None,
        report_type: str | None = None,
        limit: int = 100,
    ) -> list[ReportConfig]:
        """Get all report configurations with optional filtering."""
        results = []
        for config in self._configs.values():
            if status and config.status != status:
                continue
            if report_type and config.report_type.value != report_type:
                continue
            results.append(config)

        # Sort by created_at descending
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]

    async def get_active_configs(self) -> list[ReportConfig]:
        """Get all active report configurations."""
        return await self.get_all_configs(status=ReportStatus.ACTIVE)

    async def delete_config(self, config_id: str) -> bool:
        """Delete a report configuration."""
        async with self._lock:
            if config_id in self._configs:
                del self._configs[config_id]
                # Also delete associated outputs
                if config_id in self._outputs_by_config:
                    for output_id in self._outputs_by_config[config_id]:
                        if output_id in self._outputs:
                            del self._outputs[output_id]
                    del self._outputs_by_config[config_id]
                return True
            return False

    async def update_config_status(
        self, config_id: str, status: ReportStatus
    ) -> ReportConfig | None:
        """Update the status of a report configuration."""
        async with self._lock:
            if config_id in self._configs:
                self._configs[config_id].status = status
                self._configs[config_id].updated_at = datetime.now(UTC)
                return self._configs[config_id]
            return None

    async def update_schedule(
        self,
        config_id: str,
        next_run_at: datetime | None = None,
        last_run_at: datetime | None = None,
    ) -> ReportConfig | None:
        """Update schedule times for a report configuration."""
        async with self._lock:
            if config_id in self._configs:
                if next_run_at is not None:
                    self._configs[config_id].schedule.next_run_at = next_run_at
                if last_run_at is not None:
                    self._configs[config_id].schedule.last_run_at = last_run_at
                self._configs[config_id].updated_at = datetime.now(UTC)
                return self._configs[config_id]
            return None

    # --- Report Output Operations ---

    async def save_output(self, output: ReportOutput) -> ReportOutput:
        """Save or update a report output."""
        async with self._lock:
            self._outputs[output.id] = output
            # Track by config
            if output.report_config_id not in self._outputs_by_config:
                self._outputs_by_config[output.report_config_id] = []
            if output.id not in self._outputs_by_config[output.report_config_id]:
                self._outputs_by_config[output.report_config_id].append(output.id)
            self._trim_outputs()
            return output

    async def get_output(self, output_id: str) -> ReportOutput | None:
        """Get a report output by ID."""
        return self._outputs.get(output_id)

    async def get_outputs_for_config(
        self,
        config_id: str,
        status: ReportRunStatus | None = None,
        limit: int = 50,
    ) -> list[ReportOutput]:
        """Get all outputs for a report configuration."""
        output_ids = self._outputs_by_config.get(config_id, [])
        results = []
        for output_id in output_ids:
            output = self._outputs.get(output_id)
            if output:
                if status and output.run_status != status:
                    continue
                results.append(output)

        # Sort by triggered_at descending
        results.sort(key=lambda x: x.triggered_at, reverse=True)
        return results[:limit]

    async def get_recent_outputs(
        self,
        status: ReportRunStatus | None = None,
        limit: int = 100,
    ) -> list[ReportOutput]:
        """Get recent report outputs."""
        results = []
        for output in self._outputs.values():
            if status and output.run_status != status:
                continue
            results.append(output)

        results.sort(key=lambda x: x.triggered_at, reverse=True)
        return results[:limit]

    async def update_output_status(
        self,
        output_id: str,
        status: ReportRunStatus,
        error_message: str | None = None,
    ) -> ReportOutput | None:
        """Update the status of a report output."""
        async with self._lock:
            if output_id in self._outputs:
                self._outputs[output_id].run_status = status
                if status == ReportRunStatus.COMPLETED:
                    self._outputs[output_id].completed_at = datetime.now(UTC)
                    if self._outputs[output_id].started_at:
                        duration = (
                            datetime.now(UTC) - self._outputs[output_id].started_at
                        ).total_seconds()
                        self._outputs[output_id].duration_seconds = duration
                if error_message:
                    self._outputs[output_id].error_message = error_message
                return self._outputs[output_id]
            return None

    async def add_delivery_result(
        self,
        output_id: str,
        channel: str,
        result: dict,
    ) -> ReportOutput | None:
        """Add a delivery result to a report output."""
        async with self._lock:
            if output_id in self._outputs:
                self._outputs[output_id].delivery_results[channel] = result
                return self._outputs[output_id]
            return None

    # --- Utility Methods ---

    def _trim_outputs(self) -> None:
        """Trim outputs to max size by removing oldest items."""
        if len(self._outputs) > self._max_outputs:
            # Sort by triggered_at and remove oldest
            sorted_outputs = sorted(
                self._outputs.items(),
                key=lambda x: x[1].triggered_at,
            )
            items_to_remove = len(self._outputs) - self._max_outputs
            for output_id, _ in sorted_outputs[:items_to_remove]:
                output = self._outputs.pop(output_id, None)
                if output and output.report_config_id in self._outputs_by_config:
                    self._outputs_by_config[output.report_config_id] = [
                        oid
                        for oid in self._outputs_by_config[output.report_config_id]
                        if oid != output_id
                    ]

    async def clear(self) -> None:
        """Clear all stored data (for testing)."""
        async with self._lock:
            self._configs.clear()
            self._outputs.clear()
            self._outputs_by_config.clear()

    async def get_stats(self) -> dict:
        """Get storage statistics."""
        pending = sum(
            1 for o in self._outputs.values() if o.run_status == ReportRunStatus.PENDING
        )
        running = sum(
            1 for o in self._outputs.values() if o.run_status == ReportRunStatus.RUNNING
        )
        completed = sum(
            1
            for o in self._outputs.values()
            if o.run_status == ReportRunStatus.COMPLETED
        )
        failed = sum(
            1
            for o in self._outputs.values()
            if o.run_status in (ReportRunStatus.FAILED, ReportRunStatus.DELIVERY_FAILED)
        )

        return {
            "configs_count": len(self._configs),
            "active_configs": sum(
                1 for c in self._configs.values() if c.status == ReportStatus.ACTIVE
            ),
            "outputs_count": len(self._outputs),
            "pending_outputs": pending,
            "running_outputs": running,
            "completed_outputs": completed,
            "failed_outputs": failed,
        }


# Global report store instance
report_store = ReportStore()
