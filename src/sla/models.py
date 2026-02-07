"""SLA Tracking Models.

Pydantic v2 models for SLA policies, targets, breaches, and metrics.
Supports severity-based SLA targets with business hours awareness.
"""

from datetime import datetime, time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class SLASeverity(StrEnum):
    """SLA severity levels (P1-P4)."""

    P1 = "P1"  # Critical - system down
    P2 = "P2"  # High - major feature impacted
    P3 = "P3"  # Medium - minor feature impacted
    P4 = "P4"  # Low - cosmetic or minor issue


class SLAType(StrEnum):
    """Types of SLA metrics tracked."""

    RESPONSE = "response"  # Time to first response/acknowledgment
    RESOLUTION = "resolution"  # Time to full resolution


class SLAStatus(StrEnum):
    """Current SLA status."""

    ON_TRACK = "on_track"  # Within SLA limits
    AT_RISK = "at_risk"  # >75% of SLA time elapsed
    BREACHED = "breached"  # SLA time exceeded


class EscalationLevel(StrEnum):
    """Escalation levels for SLA breaches."""

    NONE = "none"
    WARNING = "warning"  # 75% threshold
    BREACH = "breach"  # 100% threshold
    CRITICAL = "critical"  # 150%+ threshold


class BusinessHours(BaseModel):
    """Business hours configuration for SLA calculations.
    
    When enabled, SLA timers pause outside of business hours.
    """

    enabled: bool = False
    timezone: str = "UTC"
    start_time: time = Field(default=time(9, 0))  # 09:00
    end_time: time = Field(default=time(17, 0))  # 17:00
    working_days: list[int] = Field(
        default_factory=lambda: [0, 1, 2, 3, 4],  # Mon-Fri
        description="ISO weekdays (0=Monday, 6=Sunday)",
    )
    holidays: list[str] = Field(
        default_factory=list,
        description="Holiday dates in YYYY-MM-DD format",
    )

    @field_validator("working_days")
    @classmethod
    def validate_working_days(cls, v: list[int]) -> list[int]:
        """Validate that working days are valid ISO weekdays."""
        for day in v:
            if not 0 <= day <= 6:
                raise ValueError(f"Invalid weekday: {day}. Must be 0-6.")
        return sorted(set(v))

    @field_validator("holidays")
    @classmethod
    def validate_holidays(cls, v: list[str]) -> list[str]:
        """Validate holiday date format."""
        for date_str in v:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
        return v


class SLATarget(BaseModel):
    """Individual SLA target for a specific severity and type.
    
    Defines the time limit in minutes for response or resolution.
    """

    severity: SLASeverity
    sla_type: SLAType
    target_minutes: int = Field(gt=0, description="Target time in minutes")
    warning_threshold_percent: int = Field(
        default=75,
        ge=50,
        le=99,
        description="Percentage at which to issue warning",
    )

    @property
    def warning_minutes(self) -> float:
        """Calculate warning threshold in minutes."""
        return self.target_minutes * (self.warning_threshold_percent / 100)


class SLAPolicy(BaseModel):
    """Complete SLA policy with targets for all severities.
    
    A policy defines SLA targets for an organization, team, or service.
    """

    id: str = Field(description="Unique policy identifier")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    organization_id: str
    team_id: str | None = None
    service_id: str | None = None
    
    # SLA targets by severity
    targets: list[SLATarget] = Field(default_factory=list)
    
    # Business hours configuration
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    
    # Escalation configuration
    escalation_enabled: bool = True
    escalation_contacts: list[str] = Field(
        default_factory=list,
        description="Email addresses or Slack channels for escalation",
    )
    
    # Metadata
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None

    @model_validator(mode="after")
    def validate_unique_targets(self) -> "SLAPolicy":
        """Ensure no duplicate severity+type combinations."""
        seen = set()
        for target in self.targets:
            key = (target.severity, target.sla_type)
            if key in seen:
                raise ValueError(
                    f"Duplicate target for {target.severity}/{target.sla_type}"
                )
            seen.add(key)
        return self

    def get_target(
        self, severity: SLASeverity, sla_type: SLAType
    ) -> SLATarget | None:
        """Get specific SLA target by severity and type."""
        for target in self.targets:
            if target.severity == severity and target.sla_type == sla_type:
                return target
        return None


class SLATimer(BaseModel):
    """Active SLA timer for an incident.
    
    Tracks elapsed time and pauses for business hours.
    """

    incident_id: str
    policy_id: str
    severity: SLASeverity
    sla_type: SLAType
    
    # Timing
    started_at: datetime
    target_minutes: int
    elapsed_minutes: float = 0.0
    paused: bool = False
    paused_at: datetime | None = None
    total_paused_minutes: float = 0.0
    
    # Status
    status: SLAStatus = SLAStatus.ON_TRACK
    breached_at: datetime | None = None
    completed_at: datetime | None = None
    
    @property
    def remaining_minutes(self) -> float:
        """Calculate remaining time until SLA breach."""
        return max(0, self.target_minutes - self.elapsed_minutes)

    @property
    def percent_elapsed(self) -> float:
        """Calculate percentage of SLA time elapsed."""
        if self.target_minutes == 0:
            return 100.0
        return min(100.0, (self.elapsed_minutes / self.target_minutes) * 100)

    @property
    def is_breached(self) -> bool:
        """Check if SLA has been breached."""
        return self.status == SLAStatus.BREACHED or self.elapsed_minutes >= self.target_minutes


class SLABreach(BaseModel):
    """Record of an SLA breach event.
    
    Created when an SLA timer exceeds its target time.
    """

    id: str = Field(description="Unique breach identifier")
    incident_id: str
    policy_id: str
    severity: SLASeverity
    sla_type: SLAType
    
    # Breach details
    target_minutes: int
    actual_minutes: float
    breach_amount_minutes: float = Field(
        description="How much over the SLA target"
    )
    breach_percent: float = Field(description="Percentage over target")
    
    # Escalation
    escalation_level: EscalationLevel = EscalationLevel.BREACH
    escalated_to: list[str] = Field(default_factory=list)
    escalation_sent_at: datetime | None = None
    
    # Timestamps
    breached_at: datetime
    resolved_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    
    # Context
    notes: str | None = None
    root_cause: str | None = None

    @property
    def is_resolved(self) -> bool:
        """Check if the breach has been resolved."""
        return self.resolved_at is not None


class SLAIncidentStatus(BaseModel):
    """Current SLA status for an incident.
    
    Aggregates response and resolution SLA timers.
    """

    incident_id: str
    severity: SLASeverity
    policy_id: str
    policy_name: str
    
    # Response SLA
    response_timer: SLATimer | None = None
    response_breached: bool = False
    response_completed: bool = False
    
    # Resolution SLA
    resolution_timer: SLATimer | None = None
    resolution_breached: bool = False
    resolution_completed: bool = False
    
    # Overall status
    overall_status: SLAStatus = SLAStatus.ON_TRACK
    
    # Breaches
    breaches: list[SLABreach] = Field(default_factory=list)
    
    # Timestamps
    calculated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def worst_status(self) -> SLAStatus:
        """Get the worst status across all timers."""
        statuses = []
        if self.response_timer:
            statuses.append(self.response_timer.status)
        if self.resolution_timer:
            statuses.append(self.resolution_timer.status)
        
        if not statuses:
            return SLAStatus.ON_TRACK
        
        if SLAStatus.BREACHED in statuses:
            return SLAStatus.BREACHED
        if SLAStatus.AT_RISK in statuses:
            return SLAStatus.AT_RISK
        return SLAStatus.ON_TRACK


class SLAMetrics(BaseModel):
    """SLA compliance metrics for reporting.
    
    Aggregated metrics over a time period.
    """

    # Scope
    organization_id: str
    team_id: str | None = None
    service_id: str | None = None
    policy_id: str | None = None
    
    # Time period
    period_start: datetime
    period_end: datetime
    
    # Counts
    total_incidents: int = 0
    incidents_by_severity: dict[str, int] = Field(default_factory=dict)
    
    # Response SLA
    response_sla_met: int = 0
    response_sla_breached: int = 0
    response_compliance_percent: float = 0.0
    avg_response_minutes: float | None = None
    
    # Resolution SLA
    resolution_sla_met: int = 0
    resolution_sla_breached: int = 0
    resolution_compliance_percent: float = 0.0
    avg_resolution_minutes: float | None = None
    
    # Overall
    overall_compliance_percent: float = 0.0
    
    # Trends
    compliance_trend: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Daily compliance data for trending",
    )
    
    # Top breached
    top_breached_services: list[dict[str, Any]] = Field(default_factory=list)
    
    # Generated timestamp
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    def calculate_compliance(self) -> None:
        """Calculate compliance percentages from counts."""
        total_response = self.response_sla_met + self.response_sla_breached
        total_resolution = self.resolution_sla_met + self.resolution_sla_breached
        
        if total_response > 0:
            self.response_compliance_percent = round(
                (self.response_sla_met / total_response) * 100, 2
            )
        
        if total_resolution > 0:
            self.resolution_compliance_percent = round(
                (self.resolution_sla_met / total_resolution) * 100, 2
            )
        
        total = total_response + total_resolution
        met = self.response_sla_met + self.resolution_sla_met
        
        if total > 0:
            self.overall_compliance_percent = round((met / total) * 100, 2)


class SLANotification(BaseModel):
    """SLA notification event for escalation.
    
    Tracks notifications sent for SLA warnings and breaches.
    """

    id: str
    incident_id: str
    sla_type: SLAType
    severity: SLASeverity
    escalation_level: EscalationLevel
    
    # Recipients
    recipients: list[str] = Field(default_factory=list)
    channel: str = Field(description="email, slack, pagerduty, etc.")
    
    # Message
    subject: str
    body: str
    
    # Status
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    delivered: bool = False
    delivery_error: str | None = None


# Default SLA targets by severity
DEFAULT_SLA_TARGETS = [
    # P1 - Critical
    SLATarget(severity=SLASeverity.P1, sla_type=SLAType.RESPONSE, target_minutes=15),
    SLATarget(severity=SLASeverity.P1, sla_type=SLAType.RESOLUTION, target_minutes=240),  # 4 hours
    # P2 - High
    SLATarget(severity=SLASeverity.P2, sla_type=SLAType.RESPONSE, target_minutes=30),
    SLATarget(severity=SLASeverity.P2, sla_type=SLAType.RESOLUTION, target_minutes=480),  # 8 hours
    # P3 - Medium
    SLATarget(severity=SLASeverity.P3, sla_type=SLAType.RESPONSE, target_minutes=120),  # 2 hours
    SLATarget(severity=SLASeverity.P3, sla_type=SLAType.RESOLUTION, target_minutes=1440),  # 24 hours
    # P4 - Low
    SLATarget(severity=SLASeverity.P4, sla_type=SLAType.RESPONSE, target_minutes=480),  # 8 hours
    SLATarget(severity=SLASeverity.P4, sla_type=SLAType.RESOLUTION, target_minutes=4320),  # 72 hours
]
