"""Data models for migration jobs and results."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class MigrationStatus(StrEnum):
    """Migration job status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MigrationEntityType(StrEnum):
    """Types of entities that can be migrated."""

    SERVICES = "services"
    TEAMS = "teams"
    USERS = "users"
    SCHEDULES = "schedules"
    ESCALATIONS = "escalations"
    ALERTS = "alerts"
    INTEGRATIONS = "integrations"


class EntityMigrationResult(BaseModel):
    """Result of migrating a single entity type."""

    entity_type: MigrationEntityType
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)


class MigrationPreview(BaseModel):
    """Preview of entities available for migration."""

    entity_type: MigrationEntityType
    count: int
    sample_names: list[str] = Field(default_factory=list)


class MigrationJob(BaseModel):
    """A migration job tracking import progress."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str = "opsgenie"
    status: MigrationStatus = MigrationStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    selected_entities: list[MigrationEntityType] = Field(default_factory=list)
    results: dict[str, EntityMigrationResult] = Field(default_factory=dict)
    progress_pct: float = 0.0
    error: str | None = None
    api_key_masked: str = ""

    @staticmethod
    def mask_key(api_key: str) -> str:
        """Mask an API key for storage."""
        if len(api_key) <= 8:
            return "****"
        return api_key[:4] + "****" + api_key[-4:]
