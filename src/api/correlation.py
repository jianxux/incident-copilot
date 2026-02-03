"""API endpoints for alert correlation management."""

from datetime import datetime
import uuid
import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field
from ..config import get_settings
from ..correlation import (
    AlertGroup,
    AlertGroupStatus,
    CorrelationRule,
    CorrelationStrategy,
    IncomingAlert,
)
from ..correlation.engine import get_correlation_engine

logger = structlog.get_logger()
router = APIRouter(prefix="/correlation", tags=["correlation"])


class CreateRuleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    strategy: CorrelationStrategy
    enabled: bool = True
    priority: int = Field(default=0, ge=-100, le=100)
    time_window_seconds: int = Field(default=300, ge=30, le=3600)
    services: list[str] = Field(default_factory=list)
    match_tags: list[str] = Field(default_factory=list)
    group_by_tags: list[str] = Field(default_factory=list)
    title_patterns: list[str] = Field(default_factory=list)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    suppress_duplicates: bool = True
    max_alerts_before_notify: int = Field(default=1, ge=1, le=100)
    re_notify_after_seconds: int = Field(default=1800, ge=0, le=86400)


class TestCorrelationRequest(BaseModel):
    alert_id: str = "test-alert-001"
    source: str = "manual"
    title: str
    service: str
    severity: str = "medium"
    tags: list[str] = Field(default_factory=list)


@router.post("/rules", status_code=201)
async def create_rule(request: CreateRuleRequest):
    engine = await get_correlation_engine(get_settings())
    rule = CorrelationRule(
        rule_id=f"rule_{uuid.uuid4().hex[:12]}",
        name=request.name,
        description=request.description,
        strategy=request.strategy,
        enabled=request.enabled,
        priority=request.priority,
        time_window_seconds=request.time_window_seconds,
        services=request.services,
        match_tags=request.match_tags,
        group_by_tags=request.group_by_tags,
        title_patterns=request.title_patterns,
        similarity_threshold=request.similarity_threshold,
        suppress_duplicates=request.suppress_duplicates,
        max_alerts_before_notify=request.max_alerts_before_notify,
        re_notify_after_seconds=request.re_notify_after_seconds,
    )
    created = await engine.create_rule(rule)
    return {"rule_id": created.rule_id, "name": created.name}


@router.get("/rules")
async def list_rules():
    engine = await get_correlation_engine(get_settings())
    rules = await engine.get_rules()
    return {
        "rules": [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "strategy": r.strategy.value,
                "enabled": r.enabled,
            }
            for r in rules
        ],
        "total": len(rules),
    }


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str):
    engine = await get_correlation_engine(get_settings())
    rule = await engine.store.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {
        "rule_id": rule.rule_id,
        "name": rule.name,
        "strategy": rule.strategy.value,
        "enabled": rule.enabled,
        "priority": rule.priority,
        "services": rule.services,
    }


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    engine = await get_correlation_engine(get_settings())
    if not await engine.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"deleted": True, "rule_id": rule_id}


@router.get("/groups")
async def list_groups(
    service: str | None = Query(None), limit: int = Query(100, ge=1, le=500)
):
    engine = await get_correlation_engine(get_settings())
    groups = await engine.get_active_groups(service=service, limit=limit)
    return {
        "groups": [
            {
                "group_id": g.group_id,
                "service": g.service,
                "alert_count": g.alert_count,
                "summary": g.summary,
            }
            for g in groups
        ],
        "total": len(groups),
    }


@router.get("/groups/{group_id}")
async def get_group(group_id: str):
    engine = await get_correlation_engine(get_settings())
    group = await engine.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return {
        "group_id": group.group_id,
        "rule_id": group.rule_id,
        "service": group.service,
        "alert_count": group.alert_count,
        "alert_ids": group.alert_ids,
        "summary": group.summary,
        "suppressed_count": group.suppressed_count,
        "status": group.status.value,
    }


@router.post("/groups/{group_id}/close")
async def close_group(
    group_id: str, status: AlertGroupStatus = Query(AlertGroupStatus.CLOSED)
):
    engine = await get_correlation_engine(get_settings())
    if not await engine.close_group(group_id, status=status):
        raise HTTPException(status_code=404, detail="Group not found")
    return {"closed": True, "group_id": group_id}


@router.get("/stats")
async def get_stats():
    engine = await get_correlation_engine(get_settings())
    return await engine.get_stats()


@router.post("/test")
async def test_correlation(request: TestCorrelationRequest):
    engine = await get_correlation_engine(get_settings())
    result = await engine.correlate(
        IncomingAlert(
            alert_id=request.alert_id,
            source=request.source,
            title=request.title,
            service=request.service,
            severity=request.severity,
            tags=request.tags,
            triggered_at=datetime.utcnow(),
        )
    )
    return {
        "correlated": result.correlated,
        "group_id": result.group.group_id if result.group else None,
        "new_group": result.new_group,
        "rule_matched": result.rule_matched.name if result.rule_matched else None,
        "should_notify": result.should_notify,
        "suppression_reason": result.suppression_reason,
    }


@router.post("/cleanup")
async def cleanup_stale_groups(background_tasks: BackgroundTasks):
    engine = await get_correlation_engine(get_settings())
    background_tasks.add_task(engine.cleanup_stale_groups)
    return {"status": "cleanup_scheduled"}
