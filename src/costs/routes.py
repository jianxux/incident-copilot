"""FastAPI routes for incident cost tracking."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .calculator import CostCalculator
from .factors import CostFactorConfig, get_cost_config, set_cost_config
from .models import (
    CalculateCostRequest,
    CostReport,
    ExportReportRequest,
    GenerateReportRequest,
    IncidentCost,
    ReportPeriod,
    ROIAnalysis,
    UpdateCostRequest,
)
from .reports import CostReportGenerator, cost_store

logger = structlog.get_logger()
router = APIRouter(prefix="/api/costs", tags=["costs"])


# --- Response Models ---


class CalculateCostResponse(BaseModel):
    """Response for cost calculation."""

    cost: IncidentCost
    message: str


class CostListResponse(BaseModel):
    """Response for listing costs."""

    costs: list[IncidentCost]
    total: int


class ReportResponse(BaseModel):
    """Response for report generation."""

    report: CostReport
    message: str


class ExportResponse(BaseModel):
    """Response for report export."""

    format: str
    content: str
    report_id: str


class ConfigResponse(BaseModel):
    """Response for config operations."""

    config: CostFactorConfig
    message: str


# --- Cost Calculation Endpoints ---


@router.post("/calculate", response_model=CalculateCostResponse)
async def calculate_incident_cost(
    request: CalculateCostRequest,
) -> CalculateCostResponse:
    """
    Calculate the cost of an incident.

    This endpoint calculates the total cost including engineer time,
    revenue impact, and any custom costs provided.

    Example request:
    ```json
    {
        "incident_id": "INC-12345",
        "service_name": "payments-api",
        "severity": "high",
        "incident_started_at": "2024-01-15T10:00:00Z",
        "incident_resolved_at": "2024-01-15T11:30:00Z",
        "responders": [
            {"id": "U001", "name": "Alice", "team": "platform", "role": "sre", "time_minutes": 90}
        ],
        "affected_users": 5000,
        "affected_transactions": 250
    }
    ```
    """
    calculator = CostCalculator()

    try:
        cost = await calculator.calculate_incident_cost(request)

        # Save to store
        await cost_store.save(cost)

        logger.info(
            "incident_cost_calculated",
            incident_id=request.incident_id,
            total_cost=str(cost.total_cost),
        )

        return CalculateCostResponse(
            cost=cost,
            message="Incident cost calculated successfully",
        )

    except Exception as e:
        logger.error(
            "cost_calculation_failed",
            incident_id=request.incident_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate cost: {str(e)}",
        )


@router.get("/{incident_id}", response_model=IncidentCost)
async def get_incident_cost(incident_id: str) -> IncidentCost:
    """
    Get the cost record for an incident.

    Returns the complete cost breakdown for the specified incident.
    """
    cost = await cost_store.get(incident_id)
    if not cost:
        raise HTTPException(
            status_code=404,
            detail=f"Cost record not found for incident {incident_id}",
        )
    return cost


@router.put("/{incident_id}", response_model=IncidentCost)
async def update_incident_cost(
    incident_id: str,
    request: UpdateCostRequest,
) -> IncidentCost:
    """
    Update an incident cost record.

    Allows updating responders, affected counts, custom costs, and SLA penalties.
    Only non-finalized records can be updated.
    """
    cost = await cost_store.get(incident_id)
    if not cost:
        raise HTTPException(
            status_code=404,
            detail=f"Cost record not found for incident {incident_id}",
        )

    if cost.is_finalized:
        raise HTTPException(
            status_code=400,
            detail="Cannot update a finalized cost record",
        )

    # Update fields
    if request.affected_users is not None:
        cost.affected_users = request.affected_users
    if request.affected_transactions is not None:
        cost.affected_transactions = request.affected_transactions
    if request.notes is not None:
        cost.notes = request.notes

    # Recalculate if needed
    if request.responders or request.custom_costs:
        calculator = CostCalculator()

        if request.responders:
            cost.responder_costs = await calculator._calculate_responder_costs(
                responders=request.responders,
                severity=cost.severity,
                incident_started_at=cost.incident_started_at,
            )

        cost.calculate_totals()

    await cost_store.save(cost)

    logger.info(
        "incident_cost_updated",
        incident_id=incident_id,
        total_cost=str(cost.total_cost),
    )

    return cost


@router.post("/{incident_id}/sla-penalty", response_model=IncidentCost)
async def add_sla_penalty(
    incident_id: str,
    sla_id: str,
    sla_name: str,
    breach_type: str,
    target_value: str,
    actual_value: str,
    customer_id: str | None = None,
    customer_name: str | None = None,
    customer_tier: str = "professional",
) -> IncidentCost:
    """
    Add an SLA penalty to an incident cost record.

    Example: If an SLA requires 99.9% uptime but only 99.5% was achieved,
    add the corresponding penalty.
    """
    cost = await cost_store.get(incident_id)
    if not cost:
        raise HTTPException(
            status_code=404,
            detail=f"Cost record not found for incident {incident_id}",
        )

    if cost.is_finalized:
        raise HTTPException(
            status_code=400,
            detail="Cannot modify a finalized cost record",
        )

    calculator = CostCalculator()
    cost = await calculator.add_sla_penalty(
        incident_cost=cost,
        sla_id=sla_id,
        sla_name=sla_name,
        breach_type=breach_type,
        target_value=target_value,
        actual_value=actual_value,
        customer_id=customer_id,
        customer_name=customer_name,
        customer_tier=customer_tier,
    )

    await cost_store.save(cost)
    return cost


@router.post("/{incident_id}/finalize", response_model=IncidentCost)
async def finalize_incident_cost(
    incident_id: str,
    finalized_by: str,
) -> IncidentCost:
    """
    Finalize an incident cost record.

    Once finalized, the record cannot be modified. This is typically done
    after the incident is fully resolved and all costs are accounted for.
    """
    cost = await cost_store.get(incident_id)
    if not cost:
        raise HTTPException(
            status_code=404,
            detail=f"Cost record not found for incident {incident_id}",
        )

    if cost.is_finalized:
        raise HTTPException(
            status_code=400,
            detail="Cost record is already finalized",
        )

    calculator = CostCalculator()
    cost = await calculator.finalize_cost(cost, finalized_by)

    await cost_store.save(cost)
    return cost


@router.delete("/{incident_id}")
async def delete_incident_cost(incident_id: str) -> dict:
    """
    Delete an incident cost record.

    Only non-finalized records can be deleted.
    """
    cost = await cost_store.get(incident_id)
    if not cost:
        raise HTTPException(
            status_code=404,
            detail=f"Cost record not found for incident {incident_id}",
        )

    if cost.is_finalized:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a finalized cost record",
        )

    await cost_store.delete(incident_id)

    logger.info("incident_cost_deleted", incident_id=incident_id)

    return {"message": f"Cost record for incident {incident_id} deleted"}


@router.get("", response_model=CostListResponse)
async def list_incident_costs(
    start_date: Annotated[
        datetime | None,
        Query(description="Filter by start date"),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(description="Filter by end date"),
    ] = None,
    service: Annotated[
        str | None,
        Query(description="Filter by service name"),
    ] = None,
    team: Annotated[
        str | None,
        Query(description="Filter by team"),
    ] = None,
    severity: Annotated[
        str | None,
        Query(description="Filter by severity"),
    ] = None,
    finalized: Annotated[
        bool | None,
        Query(description="Filter by finalized status"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Maximum results to return"),
    ] = 100,
) -> CostListResponse:
    """
    List incident cost records with optional filters.

    Returns costs sorted by incident start date (most recent first).
    """
    costs = await cost_store.list(
        start_date=start_date,
        end_date=end_date,
        service_name=service,
        team=team,
        severity=severity,
        is_finalized=finalized,
        limit=limit,
    )

    return CostListResponse(
        costs=costs,
        total=len(costs),
    )


# --- Report Endpoints ---


@router.post("/reports/generate", response_model=ReportResponse)
async def generate_cost_report(
    request: GenerateReportRequest,
) -> ReportResponse:
    """
    Generate a cost report for a specified period.

    Supports daily, weekly, monthly, quarterly, and yearly reports.
    Optionally filter by services or teams.

    Example request:
    ```json
    {
        "period": "monthly",
        "services": ["payments-api", "checkout-service"],
        "include_roi": true,
        "compare_previous": true,
        "top_incidents_limit": 10
    }
    ```
    """
    generator = CostReportGenerator()

    try:
        report = await generator.generate_report(request)

        logger.info(
            "cost_report_generated",
            report_id=report.report_id,
            period=request.period.value,
            total_cost=str(report.total_cost),
        )

        return ReportResponse(
            report=report,
            message="Cost report generated successfully",
        )

    except Exception as e:
        logger.error(
            "report_generation_failed",
            period=request.period.value,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate report: {str(e)}",
        )


@router.get("/reports/summary")
async def get_cost_summary(
    period: Annotated[
        ReportPeriod,
        Query(description="Report period"),
    ] = ReportPeriod.MONTHLY,
) -> dict:
    """
    Get a quick cost summary for the specified period.

    Returns key metrics without full report details.
    """
    generator = CostReportGenerator()
    request = GenerateReportRequest(
        period=period,
        include_roi=False,
        compare_previous=True,
        top_incidents_limit=5,
    )

    report = await generator.generate_report(request)

    return {
        "period": period.value,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "total_incidents": report.total_incidents,
        "total_cost": float(report.total_cost),
        "average_cost": float(report.average_cost_per_incident),
        "cost_change_percent": report.cost_change_percent,
        "top_services": [
            {"name": s.service_name, "cost": float(s.total_cost)}
            for s in report.service_summaries[:5]
        ],
        "cost_by_severity": {
            k: float(v) for k, v in report.cost_by_severity.items()
        },
    }


@router.post("/reports/{report_id}/export", response_model=ExportResponse)
async def export_cost_report(
    report_id: str,
    request: ExportReportRequest,
) -> ExportResponse:
    """
    Export a cost report in the specified format.

    Supported formats: csv, json
    """
    # For now, regenerate the report (in production, would fetch from storage)
    generator = CostReportGenerator()

    # Generate a fresh report for export
    report_request = GenerateReportRequest(
        period=ReportPeriod.MONTHLY,
        include_roi=request.include_roi,
    )
    report = await generator.generate_report(report_request)

    try:
        if request.format == "csv":
            content = await generator.export_to_csv(report)
        elif request.format == "json":
            content = await generator.export_to_json(
                report,
                include_details=request.include_details,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {request.format}",
            )

        return ExportResponse(
            format=request.format,
            content=content,
            report_id=report.report_id,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export report: {str(e)}",
        )


@router.get("/reports/export/csv")
async def export_current_report_csv(
    period: Annotated[
        ReportPeriod,
        Query(description="Report period"),
    ] = ReportPeriod.MONTHLY,
) -> PlainTextResponse:
    """
    Export the current period's cost report as CSV.

    Returns raw CSV content for download.
    """
    generator = CostReportGenerator()
    request = GenerateReportRequest(period=period)
    report = await generator.generate_report(request)

    content = await generator.export_to_csv(report)

    return PlainTextResponse(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=cost-report-{period.value}.csv"
        },
    )


@router.get("/reports/finance-export")
async def export_for_finance(
    period: Annotated[
        ReportPeriod,
        Query(description="Report period"),
    ] = ReportPeriod.MONTHLY,
) -> dict:
    """
    Export cost data formatted for finance systems.

    Returns structured data suitable for integration with accounting
    and financial reporting systems.
    """
    generator = CostReportGenerator()
    request = GenerateReportRequest(period=period, include_roi=True)
    report = await generator.generate_report(request)

    return await generator.export_for_finance(report)


# --- ROI Endpoints ---


@router.get("/roi/analysis", response_model=ROIAnalysis)
async def get_roi_analysis(
    start_date: Annotated[
        datetime | None,
        Query(description="Analysis period start"),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(description="Analysis period end"),
    ] = None,
    investment_cost: Annotated[
        float | None,
        Query(description="Total investment cost for ROI calculation"),
    ] = None,
) -> ROIAnalysis:
    """
    Get ROI analysis for incident management improvements.

    Calculates savings from reduced MTTR, revenue protection,
    and overall return on investment.
    """
    # Default to last 30 days
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        from datetime import timedelta
        start_date = end_date - timedelta(days=30)

    incidents = await cost_store.list(
        start_date=start_date,
        end_date=end_date,
        limit=10000,
    )

    calculator = CostCalculator()
    analysis = await calculator.calculate_roi_analysis(
        incidents=incidents,
        period_start=start_date,
        period_end=end_date,
        investment_cost=Decimal(str(investment_cost)) if investment_cost else None,
    )

    return analysis


# --- Config Endpoints ---


@router.get("/config", response_model=ConfigResponse)
async def get_cost_config_endpoint() -> ConfigResponse:
    """
    Get the current cost factor configuration.

    Returns hourly rates, revenue factors, SLA factors, and custom factors.
    """
    config = get_cost_config()
    return ConfigResponse(
        config=config,
        message="Current cost configuration",
    )


@router.put("/config", response_model=ConfigResponse)
async def update_cost_config(
    config: CostFactorConfig,
) -> ConfigResponse:
    """
    Update the cost factor configuration.

    Allows customizing hourly rates, revenue factors, and SLA penalties.
    Changes take effect immediately for new calculations.
    """
    set_cost_config(config)

    logger.info(
        "cost_config_updated",
        config_id=config.config_id,
        name=config.name,
    )

    return ConfigResponse(
        config=config,
        message="Cost configuration updated successfully",
    )


@router.post("/config/reset", response_model=ConfigResponse)
async def reset_cost_config() -> ConfigResponse:
    """
    Reset cost configuration to defaults.

    Restores all hourly rates, revenue factors, and SLA penalties
    to their default values.
    """
    from .factors import DefaultCostFactors

    config = DefaultCostFactors.get_default_config()
    set_cost_config(config)

    logger.info("cost_config_reset_to_defaults")

    return ConfigResponse(
        config=config,
        message="Cost configuration reset to defaults",
    )
