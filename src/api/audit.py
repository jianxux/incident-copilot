"""Audit API routes for Incident Copilot."""

from datetime import datetime, UTC
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query

from src.audit.models import AuditLogQuery, EventCategory, EventType, Outcome
from src.audit.store import audit_store

logger = structlog.get_logger()

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/events")
async def list_audit_events(
    tenant_id: str = Query(..., description="Tenant ID (required)"),
    user_id: str | None = Query(None, description="Filter by user ID"),
    event_type: str | None = Query(None, description="Filter by event type"),
    category: str | None = Query(None, description="Filter by category"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    resource_id: str | None = Query(None, description="Filter by resource ID"),
    outcome: str | None = Query(None, description="Filter by outcome"),
    start_date: datetime | None = Query(None, description="Start date for time range"),
    end_date: datetime | None = Query(None, description="End date for time range"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> dict[str, Any]:
    """List audit events with optional filters."""
    try:
        # Build query object
        event_types = None
        if event_type:
            try:
                event_types = [EventType(event_type)]
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid event type: {event_type}"
                )

        categories = None
        if category:
            try:
                categories = [EventCategory(category)]
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid category: {category}"
                )

        outcome_filter = None
        if outcome:
            try:
                outcome_filter = Outcome(outcome)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid outcome: {outcome}"
                )

        query = AuditLogQuery(
            tenant_id=tenant_id,
            user_id=user_id,
            event_types=event_types,
            categories=categories,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome_filter,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        events = await audit_store.query_events(query)

        return {
            "events": [e.model_dump() for e in events],
            "count": len(events),
            "limit": limit,
            "offset": offset,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("audit_query_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to query audit events: {e}"
        )


@router.get("/events/{event_id}")
async def get_audit_event(
    event_id: str,
    tenant_id: str = Query(..., description="Tenant ID (required)"),
) -> dict[str, Any]:
    """Get a specific audit event by ID."""
    # Query with the tenant_id and search for the specific event
    query = AuditLogQuery(tenant_id=tenant_id, limit=1000)
    events = await audit_store.query_events(query)

    for event in events:
        if event.id == event_id:
            return event.model_dump()

    raise HTTPException(status_code=404, detail="Audit event not found")


@router.get("/stats")
async def get_audit_stats(
    tenant_id: str = Query(..., description="Tenant ID (required)"),
    days: int = Query(7, ge=1, le=90, description="Number of days to include"),
) -> dict[str, Any]:
    """Get audit statistics."""
    try:
        # Build a basic query to count events
        from datetime import timedelta, UTC

        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days)

        query = AuditLogQuery(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            limit=10000,
        )

        events = await audit_store.query_events(query)
        count = await audit_store.count_events(query)

        # Calculate basic stats
        events_by_type: dict[str, int] = {}
        events_by_category: dict[str, int] = {}
        events_by_outcome: dict[str, int] = {}

        for event in events:
            events_by_type[event.event_type.value] = (
                events_by_type.get(event.event_type.value, 0) + 1
            )
            events_by_category[event.category.value] = (
                events_by_category.get(event.category.value, 0) + 1
            )
            events_by_outcome[event.outcome.value] = (
                events_by_outcome.get(event.outcome.value, 0) + 1
            )

        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_events": count,
            "events_by_type": events_by_type,
            "events_by_category": events_by_category,
            "events_by_outcome": events_by_outcome,
        }
    except Exception as e:
        logger.error("audit_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get audit stats: {e}")
