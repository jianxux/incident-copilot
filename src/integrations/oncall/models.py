"""On-Call Scheduling Models - Pydantic v2 models for schedules, shifts, and rotations."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, computed_field
from zoneinfo import ZoneInfo


class RotationType(str, Enum):
    """Rotation pattern types."""

    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    CUSTOM = "custom"


class ProviderType(str, Enum):
    """Supported on-call providers."""

    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    MANUAL = "manual"


class OverrideStatus(str, Enum):
    """Override request status."""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OnCallUser(BaseModel):
    """User on-call information."""

    id: str
    name: str
    email: str
    phone: Optional[str] = None
    slack_id: Optional[str] = None
    timezone: str = "UTC"
    avatar_url: Optional[str] = None

    def local_time(self) -> datetime:
        """Get current time in user's timezone."""
        return datetime.now(ZoneInfo(self.timezone))


class OnCallShift(BaseModel):
    """A single on-call shift."""

    id: str
    user: OnCallUser
    schedule_id: str
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"
    is_override: bool = False
    override_id: Optional[str] = None

    @computed_field
    @property
    def duration_hours(self) -> float:
        """Shift duration in hours."""
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 3600

    @computed_field
    @property
    def is_active(self) -> bool:
        """Check if shift is currently active."""
        now = datetime.now(ZoneInfo(self.timezone))
        start = (
            self.start_time
            if self.start_time.tzinfo
            else self.start_time.replace(tzinfo=ZoneInfo(self.timezone))
        )
        end = (
            self.end_time
            if self.end_time.tzinfo
            else self.end_time.replace(tzinfo=ZoneInfo(self.timezone))
        )
        return start <= now <= end

    def time_until_end(self) -> timedelta:
        """Time remaining in shift."""
        now = datetime.now(ZoneInfo(self.timezone))
        end = (
            self.end_time
            if self.end_time.tzinfo
            else self.end_time.replace(tzinfo=ZoneInfo(self.timezone))
        )
        return max(timedelta(0), end - now)


class Rotation(BaseModel):
    """Rotation configuration."""

    id: str
    name: str
    type: RotationType
    participants: list[OnCallUser]
    handoff_time: str = "09:00"  # HH:MM format
    handoff_day: Optional[int] = None  # 0=Monday for weekly
    timezone: str = "UTC"
    start_date: datetime
    layer: int = 1  # For multi-layer schedules

    def next_handoff(self) -> datetime:
        """Calculate next handoff time."""
        now = datetime.now(ZoneInfo(self.timezone))
        hour, minute = map(int, self.handoff_time.split(":"))

        if self.type == RotationType.DAILY:
            next_handoff = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_handoff <= now:
                next_handoff += timedelta(days=1)
        elif self.type == RotationType.WEEKLY:
            days_ahead = (self.handoff_day or 0) - now.weekday()
            if days_ahead < 0 or (days_ahead == 0 and now.hour >= hour):
                days_ahead += 7
            next_handoff = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            next_handoff += timedelta(days=days_ahead)
        else:
            next_handoff = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_handoff <= now:
                next_handoff += timedelta(days=1)

        return next_handoff

    def current_position(self) -> int:
        """Get current rotation position (which participant is on-call)."""
        if not self.participants:
            return 0
        now = datetime.now(ZoneInfo(self.timezone))
        start = (
            self.start_date
            if self.start_date.tzinfo
            else self.start_date.replace(tzinfo=ZoneInfo(self.timezone))
        )

        if self.type == RotationType.DAILY:
            days_elapsed = (now - start).days
            return days_elapsed % len(self.participants)
        elif self.type == RotationType.WEEKLY:
            weeks_elapsed = (now - start).days // 7
            return weeks_elapsed % len(self.participants)
        elif self.type == RotationType.BIWEEKLY:
            periods_elapsed = (now - start).days // 14
            return periods_elapsed % len(self.participants)
        return 0


class OnCallSchedule(BaseModel):
    """Complete on-call schedule."""

    id: str
    name: str
    description: Optional[str] = None
    team_id: str
    provider: ProviderType
    provider_schedule_id: Optional[str] = None
    timezone: str = "UTC"
    rotations: list[Rotation] = Field(default_factory=list)
    escalation_policy_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    sync_enabled: bool = True
    last_synced: Optional[datetime] = None

    def get_current_oncall(self) -> Optional[OnCallUser]:
        """Get the currently on-call user from primary rotation."""
        if not self.rotations:
            return None
        primary = min(self.rotations, key=lambda r: r.layer)
        pos = primary.current_position()
        if primary.participants:
            return primary.participants[pos]
        return None


class OnCallOverride(BaseModel):
    """Temporary schedule override (handoff)."""

    id: str
    schedule_id: str
    original_user: OnCallUser
    override_user: OnCallUser
    start_time: datetime
    end_time: datetime
    reason: Optional[str] = None
    status: OverrideStatus = OverrideStatus.PENDING
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    notification_sent: bool = False

    @computed_field
    @property
    def is_active(self) -> bool:
        """Check if override is currently active."""
        if self.status != OverrideStatus.ACTIVE:
            return False
        now = datetime.utcnow()
        return self.start_time <= now <= self.end_time

    def activate(self) -> None:
        """Activate the override."""
        self.status = OverrideStatus.ACTIVE

    def cancel(self) -> None:
        """Cancel the override."""
        self.status = OverrideStatus.CANCELLED


class HandoffNotification(BaseModel):
    """On-call handoff notification."""

    id: str
    schedule_id: str
    outgoing_user: OnCallUser
    incoming_user: OnCallUser
    handoff_time: datetime
    message: Optional[str] = None
    sent_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None


class OnCallHistoryEntry(BaseModel):
    """Historical on-call record."""

    id: str
    schedule_id: str
    user: OnCallUser
    start_time: datetime
    end_time: datetime
    was_override: bool = False
    incidents_handled: int = 0
    notes: Optional[str] = None


class ScheduleSyncResult(BaseModel):
    """Result of a schedule sync operation."""

    schedule_id: str
    provider: ProviderType
    success: bool
    shifts_synced: int = 0
    overrides_synced: int = 0
    errors: list[str] = Field(default_factory=list)
    synced_at: datetime = Field(default_factory=datetime.utcnow)
