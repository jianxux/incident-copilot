"""Data models for incident memory capture and recall."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class IncidentRecord(BaseModel):
    """Structured memory representation of a resolved incident."""

    id: str = Field(..., description="Unique incident memory identifier")
    title: str = Field(..., min_length=1)
    created_at: datetime
    resolved_at: datetime | None = None
    duration_minutes: int | None = None
    severity: str | None = None
    services_affected: list[str] = Field(default_factory=list)
    root_cause_category: str | None = None
    root_cause_summary: str | None = None
    error_signatures: list[str] = Field(default_factory=list)
    metric_anomalies: list[str] = Field(default_factory=list)
    deploy_involved: bool = False
    deploy_sha: str | None = None
    resolution_steps: list[str] = Field(default_factory=list)
    resolution_summary: str | None = None
    time_to_diagnose_minutes: int | None = None
    time_to_fix_minutes: int | None = None
    was_rollback: bool | None = None
    runbook_used: str | None = None
    what_helped: str | None = None
    what_was_missing: str | None = None
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] = Field(default_factory=list)


class IncidentRecallResult(BaseModel):
    """Scored recall match for a past incident."""

    record: IncidentRecord
    score: float
    vector_similarity: float
    temporal_decay: float


class ServiceCorrelation(BaseModel):
    """Pairwise service co-failure correlation."""

    service_a: str
    service_b: str
    co_occurrence_count: int = Field(ge=0)
    avg_time_gap_minutes: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)


class GeneratedRunbook(BaseModel):
    """Auto-generated runbook synthesized from recurring incident patterns."""

    id: str
    title: str
    trigger_conditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    source_incident_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    root_cause_category: str | None = None
    services_affected: list[str] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class MemoryHealthStatus(StrEnum):
    """Memory subsystem health status."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


class MemoryHealthReport(BaseModel):
    """Health summary for incident memory quality and freshness."""

    status: MemoryHealthStatus
    total_records: int = Field(ge=0)
    avg_similarity_score: float = Field(ge=0.0, le=1.0)
    capture_success_rate: float = Field(ge=0.0, le=1.0)
    zero_result_recall_rate: float = Field(ge=0.0, le=1.0)
    stale_records: int = Field(ge=0)
    days_since_last_capture: int | None = Field(default=None, ge=0)
    alerts: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
