"""Data models for incident memory capture and recall."""

from datetime import datetime

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
