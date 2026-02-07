"""FastAPI routes for incident cost management."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .models import (
    CostCategory,
    CostEntry,
    CostReport,
    CostTrend,
    Currency,
    EngineerRate,
    IncidentCost,
    ROIAnalysis,
    ServiceCriticality,
    ServiceRevenueConfig,
    SLAConfig,
    TeamCostAllocation,
)
from .service import CostService

router = APIRouter(prefix="/costs", tags=["costs"])

# Dependency for cost service
_cost_service: CostService | None = None


def get_cost_service() -> CostService:
    """Get the cost service instance."""
    global _cost_service
    if _cost_service is None:
        _cost_service = CostService()
    return _cost_service


def set_cost_service(service: CostService) -> None:
    """Set the cost service instance (for testing)."""
    global _cost_service
    _cost_service = service


# Request/Response models
class AddCostEntryRequest(BaseModel):
    """Request to add a cost entry."""

    incident_id: str
    category: CostCategory
    amount: Decimal = Field(ge=0)
    currency: Currency = Currency.USD
    description: str | None = None
    team: str | None = None
    department: str | None = None
    engineer_id: str | None = None
    engineer_name: str | None = None
    hours_spent: float | None = None
    hourly_rate: Decimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CalculateEngineerTimeRequest(BaseModel):
    """Request to calculate engineer time cost."""

    incident_id: str
    hours: float = Field(gt=0)
    engineer_id: str | None = None
    engineer_name: str | None = None
    team: str | None = None
    department: str | None = None
    level: str | None = None


class CalculateRevenueImpactRequest(BaseModel):
    """Request to calculate revenue impact."""

    incident_id: str
    service_name: str
    duration_hours: float = Field(gt=0)
    criticality: ServiceCriticality | None = None
    partial_outage_pct: float = Field(default=100.0, ge=0, le=100)


class CalculateCloudCostRequest(BaseModel):
    """Request to calculate cloud cost."""

    incident_id: str
    resource_type: str
    quantity: float = Field(default=1.0, gt=0)
    hours: float = Field(default=1.0, gt=0)
    unit_cost: Decimal | None = None


class CalculateSLAPenaltyRequest(BaseModel):
    """Request to calculate SLA penalty."""

    incident_id: str
    customer_id: str
    downtime_minutes: float = Field(gt=0)
    period_days: int = Field(default=30, gt=0)


class CalculateCustomerImpactRequest(BaseModel):
    """Request to calculate customer impact cost."""

    incident_id: str
    impact_type: str
    count: int = Field(default=1, gt=0)
    custom_cost: Decimal | None = None


class CalculateIncidentCostRequest(BaseModel):
    """Request to calculate total incident cost."""

    incident_id: str
    incident_title: str | None = None
    service_name: str | None = None
    severity: str | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None


class ROIAnalysisRequest(BaseModel):
    """Request for ROI analysis."""

    title: str
    period: str = Field(default="90d", pattern=r"^\d+d$")
    prevention_investment: Decimal = Field(gt=0)
    projected_incidents_prevented: int = Field(gt=0)
    investment_items: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None


class CostResponse(BaseModel):
    """Generic cost response."""

    success: bool = True
    data: Any = None
    message: str | None = None


# Cost Entry endpoints
@router.post("/entries", response_model=CostResponse)
async def add_cost_entry(
    request: AddCostEntryRequest,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Add a manual cost entry."""
    entry = CostEntry(
        incident_id=request.incident_id,
        category=request.category,
        amount=request.amount,
        currency=request.currency,
        description=request.description,
        team=request.team,
        department=request.department,
        engineer_id=request.engineer_id,
        engineer_name=request.engineer_name,
        hours_spent=request.hours_spent,
        hourly_rate=request.hourly_rate,
        metadata=request.metadata,
        source="manual",
    )
    entry_id = await service.add_cost_entry(entry)
    return CostResponse(data={"entry_id": entry_id})


@router.get("/entries/{entry_id}", response_model=CostResponse)
async def get_cost_entry(
    entry_id: str,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Get a cost entry by ID."""
    entry = await service.get_cost_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Cost entry not found")
    return CostResponse(data=entry.model_dump())


@router.delete("/entries/{entry_id}", response_model=CostResponse)
async def delete_cost_entry(
    entry_id: str,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Delete a cost entry."""
    deleted = await service.delete_cost_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cost entry not found")
    return CostResponse(message="Entry deleted")


# Calculator endpoints
@router.post("/calculate/engineer-time", response_model=CostResponse)
async def calculate_engineer_time(
    request: CalculateEngineerTimeRequest,
    service: Annotated[CostService, Depends(get_cost_service)],
    save: bool = Query(default=True, description="Save the calculated cost"),
) -> CostResponse:
    """Calculate engineer time cost."""
    entry = await service.calculate_engineer_time(
        incident_id=request.incident_id,
        hours=request.hours,
        engineer_id=request.engineer_id,
        engineer_name=request.engineer_name,
        team=request.team,
        department=request.department,
        level=request.level,
        save=save,
    )
    return CostResponse(data=entry.model_dump())


@router.post("/calculate/revenue-impact", response_model=CostResponse)
async def calculate_revenue_impact(
    request: CalculateRevenueImpactRequest,
    service: Annotated[CostService, Depends(get_cost_service)],
    save: bool = Query(default=True),
) -> CostResponse:
    """Calculate revenue impact cost."""
    entry = await service.calculate_revenue_impact(
        incident_id=request.incident_id,
        service_name=request.service_name,
        duration_hours=request.duration_hours,
        criticality=request.criticality,
        partial_outage_pct=request.partial_outage_pct,
        save=save,
    )
    return CostResponse(data=entry.model_dump())


@router.post("/calculate/cloud-cost", response_model=CostResponse)
async def calculate_cloud_cost(
    request: CalculateCloudCostRequest,
    service: Annotated[CostService, Depends(get_cost_service)],
    save: bool = Query(default=True),
) -> CostResponse:
    """Calculate cloud resource cost."""
    entry = await service.calculate_cloud_cost(
        incident_id=request.incident_id,
        resource_type=request.resource_type,
        quantity=request.quantity,
        hours=request.hours,
        unit_cost=request.unit_cost,
        save=save,
    )
    return CostResponse(data=entry.model_dump())


@router.post("/calculate/sla-penalty", response_model=CostResponse)
async def calculate_sla_penalty(
    request: CalculateSLAPenaltyRequest,
    service: Annotated[CostService, Depends(get_cost_service)],
    save: bool = Query(default=True),
) -> CostResponse:
    """Calculate SLA penalty cost."""
    entry = await service.calculate_sla_penalty(
        incident_id=request.incident_id,
        customer_id=request.customer_id,
        downtime_minutes=request.downtime_minutes,
        period_days=request.period_days,
        save=save,
    )
    if not entry:
        return CostResponse(data=None, message="No SLA breach or customer not found")
    return CostResponse(data=entry.model_dump())


@router.post("/calculate/customer-impact", response_model=CostResponse)
async def calculate_customer_impact(
    request: CalculateCustomerImpactRequest,
    service: Annotated[CostService, Depends(get_cost_service)],
    save: bool = Query(default=True),
) -> CostResponse:
    """Calculate customer impact cost."""
    entry = await service.calculate_customer_impact(
        incident_id=request.incident_id,
        impact_type=request.impact_type,
        count=request.count,
        custom_cost=request.custom_cost,
        save=save,
    )
    return CostResponse(data=entry.model_dump())


# Incident cost endpoints
@router.get("/incidents/{incident_id}", response_model=CostResponse)
async def get_incident_cost(
    incident_id: str,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Get aggregated cost for an incident."""
    cost = await service.get_incident_cost(incident_id)
    if not cost:
        raise HTTPException(status_code=404, detail="No costs found for incident")
    return CostResponse(data=cost.model_dump())


@router.post("/incidents/calculate", response_model=CostResponse)
async def calculate_incident_cost(
    request: CalculateIncidentCostRequest,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Calculate and aggregate total cost for an incident."""
    cost = await service.calculate_incident_cost(
        incident_id=request.incident_id,
        incident_title=request.incident_title,
        service_name=request.service_name,
        severity=request.severity,
        started_at=request.started_at,
        resolved_at=request.resolved_at,
    )
    return CostResponse(data=cost.model_dump())


# Trend and report endpoints
@router.get("/trends", response_model=CostResponse)
async def get_cost_trend(
    service: Annotated[CostService, Depends(get_cost_service)],
    period: str = Query(default="30d", pattern=r"^\d+d$"),
) -> CostResponse:
    """Get cost trend for a period."""
    trend = await service.get_cost_trend(period)
    return CostResponse(data=trend.model_dump())


@router.post("/reports", response_model=CostResponse)
async def generate_report(
    service: Annotated[CostService, Depends(get_cost_service)],
    period: str = Query(default="30d", pattern=r"^\d+d$"),
    title: str | None = Query(default=None),
) -> CostResponse:
    """Generate a comprehensive cost report."""
    report = await service.generate_report(period=period, title=title)
    return CostResponse(data=report.model_dump())


@router.get("/reports/{report_id}", response_model=CostResponse)
async def get_report(
    report_id: str,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Get a cost report by ID."""
    report = await service.store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return CostResponse(data=report.model_dump())


@router.get("/reports", response_model=CostResponse)
async def list_reports(
    service: Annotated[CostService, Depends(get_cost_service)],
    limit: int = Query(default=20, le=100),
) -> CostResponse:
    """List recent cost reports."""
    reports = await service.store.list_reports(limit)
    return CostResponse(data=[r.model_dump() for r in reports])


# ROI Analysis endpoints
@router.post("/roi", response_model=CostResponse)
async def calculate_roi(
    request: ROIAnalysisRequest,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Calculate ROI for prevention investment."""
    analysis = await service.calculate_roi(
        title=request.title,
        period=request.period,
        prevention_investment=request.prevention_investment,
        projected_incidents_prevented=request.projected_incidents_prevented,
        investment_items=request.investment_items,
        notes=request.notes,
    )
    return CostResponse(data=analysis.model_dump())


@router.get("/roi/{analysis_id}", response_model=CostResponse)
async def get_roi_analysis(
    analysis_id: str,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Get an ROI analysis by ID."""
    analysis = await service.store.get_roi_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="ROI analysis not found")
    return CostResponse(data=analysis.model_dump())


# Team allocation endpoints
@router.get("/teams/{team}/allocation", response_model=CostResponse)
async def get_team_allocation(
    team: str,
    service: Annotated[CostService, Depends(get_cost_service)],
    period: str = Query(default="30d", pattern=r"^\d+d$"),
) -> CostResponse:
    """Get cost allocation for a team."""
    allocation = await service.calculate_team_allocation(team, period)
    return CostResponse(data=allocation.model_dump())


@router.get("/teams/allocations", response_model=CostResponse)
async def list_team_allocations(
    service: Annotated[CostService, Depends(get_cost_service)],
    period: str = Query(default="30d", pattern=r"^\d+d$"),
) -> CostResponse:
    """List all team allocations for a period."""
    allocations = await service.store.get_all_team_allocations(period)
    return CostResponse(data=[a.model_dump() for a in allocations])


# Comparison endpoint
@router.get("/compare", response_model=CostResponse)
async def compare_periods(
    service: Annotated[CostService, Depends(get_cost_service)],
    period1: str = Query(default="30d", pattern=r"^\d+d$"),
    period2: str = Query(default="30d", pattern=r"^\d+d$"),
) -> CostResponse:
    """Compare costs between two periods."""
    comparison = await service.compare_periods(period1, period2)
    return CostResponse(data=comparison)


# Configuration endpoints
@router.post("/config/engineer-rates", response_model=CostResponse)
async def configure_engineer_rate(
    rate: EngineerRate,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Configure an engineer rate."""
    rate_id = await service.configure_engineer_rate(rate)
    return CostResponse(data={"rate_id": rate_id})


@router.get("/config/engineer-rates", response_model=CostResponse)
async def list_engineer_rates(
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """List all engineer rates."""
    rates = await service.store.get_all_engineer_rates()
    return CostResponse(data=[r.model_dump() for r in rates])


@router.post("/config/services", response_model=CostResponse)
async def configure_service(
    config: ServiceRevenueConfig,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Configure a service revenue config."""
    service_name = await service.configure_service(config)
    return CostResponse(data={"service_name": service_name})


@router.get("/config/services", response_model=CostResponse)
async def list_service_configs(
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """List all service configurations."""
    configs = await service.store.get_all_service_configs()
    return CostResponse(data=[c.model_dump() for c in configs])


@router.post("/config/sla", response_model=CostResponse)
async def configure_sla(
    config: SLAConfig,
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """Configure an SLA."""
    config_id = await service.configure_sla(config)
    return CostResponse(data={"config_id": config_id})


@router.get("/config/sla", response_model=CostResponse)
async def list_sla_configs(
    service: Annotated[CostService, Depends(get_cost_service)],
) -> CostResponse:
    """List all SLA configurations."""
    configs = await service.store.get_all_sla_configs()
    return CostResponse(data=[c.model_dump() for c in configs])
