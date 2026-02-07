"""
Change Tracking Models - Track deployments, config changes, and feature flags.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ChangeType(StrEnum):
    """Types of changes that can be tracked."""

    DEPLOYMENT = "deployment"
    CONFIG_CHANGE = "config_change"
    FEATURE_FLAG = "feature_flag"
    DATABASE_MIGRATION = "database_migration"
    INFRASTRUCTURE = "infrastructure"
    ROLLBACK = "rollback"


class ChangeStatus(StrEnum):
    """Status of a change event."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ChangeSource(StrEnum):
    """Source systems for change events."""

    GITHUB = "github"
    GITLAB = "gitlab"
    ARGOCD = "argocd"
    LAUNCHDARKLY = "launchdarkly"
    KUBERNETES = "kubernetes"
    TERRAFORM = "terraform"
    MANUAL = "manual"


class RiskLevel(StrEnum):
    """Risk level assessment for changes."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeEvent(BaseModel):
    """Base model for all change events."""

    id: str = Field(..., description="Unique identifier for the change")
    type: ChangeType
    source: ChangeSource
    status: ChangeStatus = ChangeStatus.COMPLETED

    title: str = Field(..., description="Short description of the change")
    description: str | None = Field(None, description="Detailed description")

    # Timing
    started_at: datetime
    completed_at: datetime | None = None

    # Attribution
    author: str = Field(..., description="Who made the change")
    author_email: str | None = None

    # Context
    environment: str = Field(default="production")
    service: str | None = Field(None, description="Affected service")
    services: list[str] = Field(
        default_factory=list, description="All affected services"
    )

    # Impact assessment
    risk_level: RiskLevel = RiskLevel.MEDIUM
    impact_score: float = Field(default=0.5, ge=0.0, le=1.0)

    # Linking
    commit_sha: str | None = None
    pr_number: int | None = None
    ticket_id: str | None = None
    external_url: str | None = None

    # Rollback tracking
    is_rollback: bool = False
    rollback_of: str | None = Field(None, description="ID of change being rolled back")
    rolled_back_by: str | None = Field(None, description="ID of rollback change")

    # Metadata
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class Deployment(ChangeEvent):
    """Deployment-specific change event."""

    type: ChangeType = ChangeType.DEPLOYMENT

    # Deployment details
    version: str = Field(..., description="Version being deployed")
    previous_version: str | None = None

    # Container/artifact info
    image: str | None = Field(None, description="Container image")
    artifact_url: str | None = None

    # Deployment strategy
    strategy: str = Field(default="rolling", description="rolling, blue-green, canary")
    canary_percentage: int | None = Field(None, ge=0, le=100)

    # Cluster info
    cluster: str | None = None
    namespace: str | None = None
    replicas: int | None = None

    # Changes included
    commits: list[str] = Field(default_factory=list)
    pr_numbers: list[int] = Field(default_factory=list)

    def calculate_impact(self) -> float:
        """Calculate deployment impact score."""
        score = 0.3  # Base score

        # Multiple services = higher impact
        if len(self.services) > 3:
            score += 0.2
        elif len(self.services) > 1:
            score += 0.1

        # Production = higher impact
        if self.environment == "production":
            score += 0.2

        # Many commits = higher impact
        if len(self.commits) > 10:
            score += 0.2
        elif len(self.commits) > 5:
            score += 0.1

        # Rollback = higher impact
        if self.is_rollback:
            score += 0.1

        return min(score, 1.0)


class ConfigChange(ChangeEvent):
    """Configuration change event."""

    type: ChangeType = ChangeType.CONFIG_CHANGE

    # Config details
    config_key: str = Field(..., description="Configuration key changed")
    old_value: str | None = Field(
        None, description="Previous value (redacted if sensitive)"
    )
    new_value: str | None = Field(None, description="New value (redacted if sensitive)")
    is_sensitive: bool = Field(default=False)

    # Scope
    scope: str = Field(default="service", description="service, cluster, global")

    # Validation
    validated: bool = False
    validation_errors: list[str] = Field(default_factory=list)


class FeatureFlag(ChangeEvent):
    """Feature flag change event."""

    type: ChangeType = ChangeType.FEATURE_FLAG
    source: ChangeSource = ChangeSource.LAUNCHDARKLY

    # Flag details
    flag_key: str = Field(..., description="Feature flag key")
    flag_name: str | None = None

    # State change
    previous_state: bool | None = None
    new_state: bool

    # Targeting
    targeting_rules: list[dict] = Field(default_factory=list)
    percentage_rollout: int | None = Field(None, ge=0, le=100)

    # Affected users
    affected_users: int | None = None
    affected_percentage: float | None = None

    # Prerequisites
    prerequisites: list[str] = Field(default_factory=list)


class ChangeFreeze(BaseModel):
    """Change freeze period definition."""

    id: str
    name: str
    reason: str

    start_time: datetime
    end_time: datetime

    # Scope
    environments: list[str] = Field(default_factory=lambda: ["production"])
    services: list[str] = Field(
        default_factory=list, description="Empty = all services"
    )

    # Exceptions
    allowed_change_types: list[ChangeType] = Field(default_factory=list)
    exception_approvers: list[str] = Field(default_factory=list)

    # Status
    is_active: bool = True
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def is_in_effect(self, at_time: datetime | None = None) -> bool:
        """Check if freeze is in effect at given time."""
        check_time = at_time or datetime.utcnow()
        return self.is_active and self.start_time <= check_time <= self.end_time

    def blocks_change(self, change: ChangeEvent) -> bool:
        """Check if this freeze blocks a given change."""
        if not self.is_in_effect(change.started_at):
            return False

        if change.environment not in self.environments:
            return False

        if self.services and change.service not in self.services:
            return False

        if change.type in self.allowed_change_types:
            return False

        return True


class ChangeCorrelation(BaseModel):
    """Correlation between an incident and changes."""

    incident_id: str
    incident_started_at: datetime

    # Correlated changes
    changes: list[ChangeEvent] = Field(default_factory=list)

    # Time window
    window_start: datetime
    window_end: datetime

    # Analysis
    most_likely_cause: str | None = Field(
        None, description="ID of most likely causal change"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Statistics
    total_changes: int = 0
    deployments: int = 0
    config_changes: int = 0
    feature_flags: int = 0

    def analyze(self) -> None:
        """Analyze changes and update statistics."""
        self.total_changes = len(self.changes)
        self.deployments = sum(
            1 for c in self.changes if c.type == ChangeType.DEPLOYMENT
        )
        self.config_changes = sum(
            1 for c in self.changes if c.type == ChangeType.CONFIG_CHANGE
        )
        self.feature_flags = sum(
            1 for c in self.changes if c.type == ChangeType.FEATURE_FLAG
        )

        if self.changes:
            # Find highest impact change as most likely cause
            sorted_changes = sorted(
                self.changes, key=lambda c: c.impact_score, reverse=True
            )
            self.most_likely_cause = sorted_changes[0].id
            self.confidence = sorted_changes[0].impact_score


class ChangeTimeline(BaseModel):
    """Timeline of changes for visualization."""

    start_time: datetime
    end_time: datetime

    events: list[ChangeEvent] = Field(default_factory=list)

    # Aggregations
    by_type: dict[str, int] = Field(default_factory=dict)
    by_service: dict[str, int] = Field(default_factory=dict)
    by_environment: dict[str, int] = Field(default_factory=dict)

    # Active freezes during this period
    active_freezes: list[ChangeFreeze] = Field(default_factory=list)

    def aggregate(self) -> None:
        """Compute aggregations from events."""
        self.by_type = {}
        self.by_service = {}
        self.by_environment = {}

        for event in self.events:
            # By type
            self.by_type[event.type.value] = self.by_type.get(event.type.value, 0) + 1

            # By service
            if event.service:
                self.by_service[event.service] = (
                    self.by_service.get(event.service, 0) + 1
                )

            # By environment
            self.by_environment[event.environment] = (
                self.by_environment.get(event.environment, 0) + 1
            )
