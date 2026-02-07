"""Maintenance Windows - Pydantic Models"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class ScopeType(str, Enum):
    SERVICE = "service"
    TEAM = "team"
    INFRASTRUCTURE = "infrastructure"
    GLOBAL = "global"


class MaintenanceStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXTENDED = "extended"


class NotificationType(str, Enum):
    SCHEDULED = "scheduled"
    REMINDER = "reminder"
    STARTED = "started"
    EXTENDED = "extended"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MaintenanceScope(BaseModel):
    """Defines what is affected by a maintenance window."""

    scope_type: ScopeType
    identifiers: list[str] = Field(default_factory=list)
    exclude_identifiers: list[str] = Field(default_factory=list)
    suppress_alerts: bool = True
    suppress_incidents: bool = False

    def matches(self, scope_type: ScopeType, identifier: str) -> bool:
        if self.scope_type == ScopeType.GLOBAL:
            return identifier not in self.exclude_identifiers
        if self.scope_type != scope_type or identifier in self.exclude_identifiers:
            return False
        return not self.identifiers or identifier in self.identifiers


class MaintenanceSchedule(BaseModel):
    """Schedule for maintenance windows with RRULE support."""

    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"
    is_recurring: bool = False
    rrule: Optional[str] = None
    recurrence_end: Optional[datetime] = None

    @field_validator("rrule")
    @classmethod
    def validate_rrule(cls, v: Optional[str]) -> Optional[str]:
        if v and not any(v.upper().startswith(p) for p in ("FREQ=", "RRULE:")):
            raise ValueError("RRULE must start with FREQ= or RRULE:")
        return v.upper().replace("RRULE:", "") if v else None

    @model_validator(mode="after")
    def validate_schedule(self) -> "MaintenanceSchedule":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.is_recurring and not self.rrule:
            raise ValueError("rrule required for recurring schedules")
        return self

    @property
    def duration(self) -> timedelta:
        return self.end_time - self.start_time


class ApprovalRecord(BaseModel):
    approver_id: str
    approved_at: datetime = Field(default_factory=datetime.utcnow)
    approved: bool
    comment: Optional[str] = None


class MaintenanceWindow(BaseModel):
    """A scheduled maintenance window."""

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    scope: MaintenanceScope
    schedule: MaintenanceSchedule
    status: MaintenanceStatus = MaintenanceStatus.DRAFT
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    requires_approval: bool = True
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    required_approvers: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    notification_minutes_before: list[int] = Field(default_factory=lambda: [60, 15])
    original_end_time: Optional[datetime] = None
    extension_count: int = 0
    extension_reason: Optional[str] = None
    related_incident_ids: list[str] = Field(default_factory=list)
    annotations: list[str] = Field(default_factory=list)

    def is_approved(self) -> bool:
        if not self.requires_approval:
            return True
        approved_by = {a.approver_id for a in self.approvals if a.approved}
        return (
            bool(approved_by)
            if not self.required_approvers
            else all(a in approved_by for a in self.required_approvers)
        )

    def is_active(self, at_time: Optional[datetime] = None) -> bool:
        now = at_time or datetime.utcnow()
        return (
            self.status in (MaintenanceStatus.IN_PROGRESS, MaintenanceStatus.EXTENDED)
            and self.schedule.start_time <= now <= self.schedule.end_time
        )


class MaintenanceWindowCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    scope: MaintenanceScope
    schedule: MaintenanceSchedule
    requires_approval: bool = True
    required_approvers: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    notification_minutes_before: list[int] = Field(default_factory=lambda: [60, 15])


class MaintenanceWindowUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    scope: Optional[MaintenanceScope] = None
    schedule: Optional[MaintenanceSchedule] = None
    stakeholders: Optional[list[str]] = None


class ExtendMaintenanceRequest(BaseModel):
    extend_minutes: int = Field(..., gt=0, le=480)
    reason: str = Field(..., min_length=1)


class MaintenanceNotification(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    window_id: UUID
    notification_type: NotificationType
    recipients: list[str]
    message: str
    sent_at: Optional[datetime] = None
    scheduled_for: datetime


class OverlapWarning(BaseModel):
    window_id: UUID
    overlapping_window_id: UUID
    overlap_start: datetime
    overlap_end: datetime
    shared_scope: list[str]
