"""Cost data storage with in-memory and persistent backends."""

import json
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from .models import (
    CostCategory,
    CostEntry,
    CostReport,
    EngineerRate,
    IncidentCost,
    ROIAnalysis,
    SLAConfig,
    ServiceRevenueConfig,
    TeamCostAllocation,
)


class CostStore(Protocol):
    """Protocol for cost storage backends."""

    async def save_entry(self, entry: CostEntry) -> str: ...
    async def get_entry(self, entry_id: str) -> CostEntry | None: ...
    async def get_entries_for_incident(self, incident_id: str) -> list[CostEntry]: ...
    async def get_entries_by_date_range(
        self, start: datetime, end: datetime
    ) -> list[CostEntry]: ...
    async def delete_entry(self, entry_id: str) -> bool: ...


class InMemoryCostStore:
    """In-memory cost storage for development and testing."""

    def __init__(self):
        self._entries: dict[str, CostEntry] = {}
        self._incident_costs: dict[str, IncidentCost] = {}
        self._reports: dict[str, CostReport] = {}
        self._engineer_rates: dict[str, EngineerRate] = {}
        self._service_configs: dict[str, ServiceRevenueConfig] = {}
        self._sla_configs: dict[str, SLAConfig] = {}
        self._roi_analyses: dict[str, ROIAnalysis] = {}
        self._team_allocations: dict[str, TeamCostAllocation] = {}

    # Cost Entry operations
    async def save_entry(self, entry: CostEntry) -> str:
        """Save a cost entry."""
        if not entry.id:
            entry.id = str(uuid.uuid4())
        self._entries[entry.id] = entry
        return entry.id

    async def get_entry(self, entry_id: str) -> CostEntry | None:
        """Get a cost entry by ID."""
        return self._entries.get(entry_id)

    async def get_entries_for_incident(self, incident_id: str) -> list[CostEntry]:
        """Get all cost entries for an incident."""
        return [e for e in self._entries.values() if e.incident_id == incident_id]

    async def get_entries_by_date_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[CostEntry]:
        """Get entries within a date range."""
        return [e for e in self._entries.values() if start <= e.created_at <= end]

    async def get_entries_by_category(
        self,
        category: CostCategory,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[CostEntry]:
        """Get entries by category."""
        entries = [e for e in self._entries.values() if e.category == category]
        if start:
            entries = [e for e in entries if e.created_at >= start]
        if end:
            entries = [e for e in entries if e.created_at <= end]
        return entries

    async def get_entries_by_team(
        self,
        team: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[CostEntry]:
        """Get entries by team."""
        entries = [e for e in self._entries.values() if e.team == team]
        if start:
            entries = [e for e in entries if e.created_at >= start]
        if end:
            entries = [e for e in entries if e.created_at <= end]
        return entries

    async def delete_entry(self, entry_id: str) -> bool:
        """Delete a cost entry."""
        if entry_id in self._entries:
            del self._entries[entry_id]
            return True
        return False

    # Incident Cost operations
    async def save_incident_cost(self, cost: IncidentCost) -> str:
        """Save aggregated incident cost."""
        self._incident_costs[cost.incident_id] = cost
        return cost.incident_id

    async def get_incident_cost(self, incident_id: str) -> IncidentCost | None:
        """Get aggregated cost for an incident."""
        return self._incident_costs.get(incident_id)

    async def get_all_incident_costs(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[IncidentCost]:
        """Get all incident costs, optionally filtered by date."""
        costs = list(self._incident_costs.values())
        if start:
            costs = [c for c in costs if c.started_at and c.started_at >= start]
        if end:
            costs = [c for c in costs if c.started_at and c.started_at <= end]
        return costs

    # Report operations
    async def save_report(self, report: CostReport) -> str:
        """Save a cost report."""
        self._reports[report.report_id] = report
        return report.report_id

    async def get_report(self, report_id: str) -> CostReport | None:
        """Get a cost report by ID."""
        return self._reports.get(report_id)

    async def list_reports(self, limit: int = 20) -> list[CostReport]:
        """List recent reports."""
        reports = sorted(
            self._reports.values(),
            key=lambda r: r.generated_at,
            reverse=True,
        )
        return reports[:limit]

    # Configuration operations
    async def save_engineer_rate(self, rate: EngineerRate) -> str:
        """Save engineer rate configuration."""
        self._engineer_rates[rate.id] = rate
        return rate.id

    async def get_engineer_rate(self, rate_id: str) -> EngineerRate | None:
        """Get engineer rate by ID."""
        return self._engineer_rates.get(rate_id)

    async def get_all_engineer_rates(self) -> list[EngineerRate]:
        """Get all engineer rates."""
        return list(self._engineer_rates.values())

    async def save_service_config(self, config: ServiceRevenueConfig) -> str:
        """Save service revenue configuration."""
        self._service_configs[config.service_name] = config
        return config.service_name

    async def get_service_config(
        self, service_name: str
    ) -> ServiceRevenueConfig | None:
        """Get service configuration."""
        return self._service_configs.get(service_name)

    async def get_all_service_configs(self) -> list[ServiceRevenueConfig]:
        """Get all service configurations."""
        return list(self._service_configs.values())

    async def save_sla_config(self, config: SLAConfig) -> str:
        """Save SLA configuration."""
        self._sla_configs[config.id] = config
        return config.id

    async def get_sla_config(self, config_id: str) -> SLAConfig | None:
        """Get SLA configuration."""
        return self._sla_configs.get(config_id)

    async def get_all_sla_configs(self) -> list[SLAConfig]:
        """Get all SLA configurations."""
        return list(self._sla_configs.values())

    # ROI Analysis operations
    async def save_roi_analysis(self, analysis: ROIAnalysis) -> str:
        """Save ROI analysis."""
        self._roi_analyses[analysis.analysis_id] = analysis
        return analysis.analysis_id

    async def get_roi_analysis(self, analysis_id: str) -> ROIAnalysis | None:
        """Get ROI analysis."""
        return self._roi_analyses.get(analysis_id)

    async def list_roi_analyses(self, limit: int = 20) -> list[ROIAnalysis]:
        """List ROI analyses."""
        return list(self._roi_analyses.values())[:limit]

    # Team allocation operations
    async def save_team_allocation(self, allocation: TeamCostAllocation) -> str:
        """Save team cost allocation."""
        key = f"{allocation.team}:{allocation.period}"
        self._team_allocations[key] = allocation
        return key

    async def get_team_allocation(
        self, team: str, period: str
    ) -> TeamCostAllocation | None:
        """Get team allocation."""
        return self._team_allocations.get(f"{team}:{period}")

    async def get_all_team_allocations(
        self, period: str | None = None
    ) -> list[TeamCostAllocation]:
        """Get all team allocations, optionally filtered by period."""
        allocations = list(self._team_allocations.values())
        if period:
            allocations = [a for a in allocations if a.period == period]
        return allocations


class FileCostStore(InMemoryCostStore):
    """File-based cost storage with JSON persistence."""

    def __init__(self, data_dir: Path):
        super().__init__()
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._entries_file = data_dir / "cost_entries.json"
        self._incident_costs_file = data_dir / "incident_costs.json"
        self._reports_file = data_dir / "cost_reports.json"
        self._config_file = data_dir / "cost_config.json"
        self._load()

    def _load(self) -> None:
        """Load data from files."""
        self._load_entries()
        self._load_incident_costs()
        self._load_reports()
        self._load_config()

    def _load_entries(self) -> None:
        """Load cost entries from file."""
        if self._entries_file.exists():
            with open(self._entries_file) as f:
                data = json.load(f)
                for item in data:
                    # Convert Decimal fields
                    item["amount"] = Decimal(item["amount"])
                    if item.get("hourly_rate"):
                        item["hourly_rate"] = Decimal(item["hourly_rate"])
                    item["created_at"] = datetime.fromisoformat(item["created_at"])
                    entry = CostEntry(**item)
                    self._entries[entry.id] = entry

    def _load_incident_costs(self) -> None:
        """Load incident costs from file."""
        if self._incident_costs_file.exists():
            with open(self._incident_costs_file) as f:
                data = json.load(f)
                for item in data:
                    item["total_cost"] = Decimal(item["total_cost"])
                    item["totals_by_category"] = {
                        CostCategory(k): Decimal(v)
                        for k, v in item.get("totals_by_category", {}).items()
                    }
                    if item.get("started_at"):
                        item["started_at"] = datetime.fromisoformat(item["started_at"])
                    if item.get("resolved_at"):
                        item["resolved_at"] = datetime.fromisoformat(
                            item["resolved_at"]
                        )
                    item["calculated_at"] = datetime.fromisoformat(
                        item["calculated_at"]
                    )
                    # Reconstruct entries
                    entries = []
                    for entry_data in item.get("entries", []):
                        entry_data["amount"] = Decimal(entry_data["amount"])
                        if entry_data.get("hourly_rate"):
                            entry_data["hourly_rate"] = Decimal(
                                entry_data["hourly_rate"]
                            )
                        entry_data["created_at"] = datetime.fromisoformat(
                            entry_data["created_at"]
                        )
                        entries.append(CostEntry(**entry_data))
                    item["entries"] = entries
                    cost = IncidentCost(**item)
                    self._incident_costs[cost.incident_id] = cost

    def _load_reports(self) -> None:
        """Load reports from file."""
        if self._reports_file.exists():
            with open(self._reports_file) as f:
                data = json.load(f)
                for item in data:
                    item["total_cost"] = Decimal(item["total_cost"])
                    item["avg_cost_per_incident"] = Decimal(
                        item["avg_cost_per_incident"]
                    )
                    item["start_date"] = datetime.fromisoformat(item["start_date"])
                    item["end_date"] = datetime.fromisoformat(item["end_date"])
                    item["generated_at"] = datetime.fromisoformat(item["generated_at"])
                    item["by_category"] = {
                        CostCategory(k): Decimal(v)
                        for k, v in item.get("by_category", {}).items()
                    }
                    item["by_severity"] = {
                        k: Decimal(v) for k, v in item.get("by_severity", {}).items()
                    }
                    item["by_service"] = {
                        k: Decimal(v) for k, v in item.get("by_service", {}).items()
                    }
                    item["by_team"] = {
                        k: Decimal(v) for k, v in item.get("by_team", {}).items()
                    }
                    item["by_department"] = {
                        k: Decimal(v) for k, v in item.get("by_department", {}).items()
                    }
                    report = CostReport(**item)
                    self._reports[report.report_id] = report

    def _load_config(self) -> None:
        """Load configuration from file."""
        if self._config_file.exists():
            with open(self._config_file) as f:
                data = json.load(f)

                for item in data.get("engineer_rates", []):
                    item["hourly_rate"] = Decimal(item["hourly_rate"])
                    item["effective_from"] = datetime.fromisoformat(
                        item["effective_from"]
                    )
                    if item.get("effective_to"):
                        item["effective_to"] = datetime.fromisoformat(
                            item["effective_to"]
                        )
                    rate = EngineerRate(**item)
                    self._engineer_rates[rate.id] = rate

                for item in data.get("service_configs", []):
                    item["hourly_revenue_impact"] = Decimal(
                        item["hourly_revenue_impact"]
                    )
                    if item.get("monthly_revenue"):
                        item["monthly_revenue"] = Decimal(item["monthly_revenue"])
                    config = ServiceRevenueConfig(**item)
                    self._service_configs[config.service_name] = config

                for item in data.get("sla_configs", []):
                    item["penalty_per_violation_pct"] = Decimal(
                        item["penalty_per_violation_pct"]
                    )
                    item["monthly_fee"] = Decimal(item["monthly_fee"])
                    item["max_penalty_pct"] = Decimal(item["max_penalty_pct"])
                    config = SLAConfig(**item)
                    self._sla_configs[config.id] = config

    async def _save_entries(self) -> None:
        """Save entries to file."""
        data = []
        for entry in self._entries.values():
            item = entry.model_dump()
            item["amount"] = str(item["amount"])
            if item.get("hourly_rate"):
                item["hourly_rate"] = str(item["hourly_rate"])
            item["created_at"] = item["created_at"].isoformat()
            data.append(item)

        with open(self._entries_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    async def _save_incident_costs(self) -> None:
        """Save incident costs to file."""
        data = []
        for cost in self._incident_costs.values():
            item = cost.model_dump()
            item["total_cost"] = str(item["total_cost"])
            item["totals_by_category"] = {
                k: str(v) for k, v in item["totals_by_category"].items()
            }
            if item.get("started_at"):
                item["started_at"] = item["started_at"].isoformat()
            if item.get("resolved_at"):
                item["resolved_at"] = item["resolved_at"].isoformat()
            item["calculated_at"] = item["calculated_at"].isoformat()
            # Serialize entries
            entries = []
            for entry in item.get("entries", []):
                entry["amount"] = str(entry["amount"])
                if entry.get("hourly_rate"):
                    entry["hourly_rate"] = str(entry["hourly_rate"])
                entry["created_at"] = entry["created_at"].isoformat()
                entries.append(entry)
            item["entries"] = entries
            data.append(item)

        with open(self._incident_costs_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    async def save_entry(self, entry: CostEntry) -> str:
        """Save entry and persist to file."""
        entry_id = await super().save_entry(entry)
        await self._save_entries()
        return entry_id

    async def delete_entry(self, entry_id: str) -> bool:
        """Delete entry and persist to file."""
        result = await super().delete_entry(entry_id)
        if result:
            await self._save_entries()
        return result

    async def save_incident_cost(self, cost: IncidentCost) -> str:
        """Save incident cost and persist."""
        result = await super().save_incident_cost(cost)
        await self._save_incident_costs()
        return result
