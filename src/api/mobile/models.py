"""Lightweight Pydantic v2 models optimized for mobile bandwidth."""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Platform(str, Enum):
    IOS = "ios"
    ANDROID = "android"


class QuickActionType(str, Enum):
    ACKNOWLEDGE = "acknowledge"
    RESOLVE = "resolve"
    ESCALATE = "escalate"
    COMMENT = "comment"
    SNOOZE = "snooze"


class MobileBaseModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True, use_enum_values=True, extra="ignore"
    )


# === Incident Models ===


class IncidentMinimal(MobileBaseModel):
    """Minimal incident for list views."""

    id: str
    title: str = Field(max_length=100)
    severity: Severity
    status: IncidentStatus
    ts: int
    unread: bool = False


class IncidentCompact(IncidentMinimal):
    """Compact incident with more fields."""

    service: str | None = None
    assignee: str | None = None
    ack_by: str | None = Field(None, alias="ackBy")
    comment_count: int = Field(0, alias="commentCount")


class IncidentFull(IncidentCompact):
    """Full incident details."""

    description: str | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    resolved_at: datetime | None = Field(None, alias="resolvedAt")
    labels: list[str] = []
    runbook_url: str | None = Field(None, alias="runbookUrl")


class PaginationMeta(MobileBaseModel):
    cursor: str | None = None
    has_more: bool = Field(alias="hasMore")
    total: int | None = None


class IncidentListResponse(MobileBaseModel):
    items: list[IncidentMinimal | IncidentCompact]
    meta: PaginationMeta
    etag: str | None = None
    last_modified: int | None = Field(None, alias="lastModified")


# === Actions ===


class QuickActionRequest(MobileBaseModel):
    action: QuickActionType
    incident_id: str = Field(alias="incidentId")
    message: str | None = Field(None, max_length=500)
    escalate_to: str | None = Field(None, alias="escalateTo")
    snooze_minutes: int | None = Field(None, alias="snoozeMinutes", ge=5, le=1440)


class QuickActionResponse(MobileBaseModel):
    success: bool
    incident_id: str = Field(alias="incidentId")
    new_status: IncidentStatus | None = Field(None, alias="newStatus")
    message: str | None = None
    ts: int


class BulkActionRequest(MobileBaseModel):
    action: QuickActionType
    incident_ids: list[str] = Field(alias="incidentIds", min_length=1, max_length=50)
    message: str | None = Field(None, max_length=500)


class BulkActionResponse(MobileBaseModel):
    succeeded: list[str]
    failed: list[dict[str, str]]


# === Dashboard ===


class SeverityCount(MobileBaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class DashboardSummary(MobileBaseModel):
    open_count: int = Field(alias="openCount")
    ack_count: int = Field(alias="ackCount")
    my_incidents: int = Field(alias="myIncidents")
    by_severity: SeverityCount = Field(alias="bySeverity")
    mttr_hours: float | None = Field(None, alias="mttrHours")
    ts: int


# === Auth ===


class TokenRefreshRequest(MobileBaseModel):
    refresh_token: str = Field(alias="refreshToken")
    device_id: str = Field(alias="deviceId")


class TokenRefreshResponse(MobileBaseModel):
    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    expires_in: int = Field(alias="expiresIn")
    biometric_hint: bool = Field(False, alias="biometricHint")


class BiometricAuthRequest(MobileBaseModel):
    device_id: str = Field(alias="deviceId")
    challenge: str
    signature: str


# === Push ===


class DeviceRegistration(MobileBaseModel):
    device_id: str = Field(alias="deviceId")
    token: str
    platform: Platform
    app_version: str = Field(alias="appVersion")
    os_version: str = Field(alias="osVersion")
    locale: str = "en"


class DeviceRegistrationResponse(MobileBaseModel):
    success: bool
    device_id: str = Field(alias="deviceId")
    expires_at: int | None = Field(None, alias="expiresAt")


class NotificationPreferences(MobileBaseModel):
    device_id: str = Field(alias="deviceId")
    enabled: bool = True
    critical_only: bool = Field(False, alias="criticalOnly")
    quiet_hours_start: int | None = Field(None, alias="quietHoursStart", ge=0, le=23)
    quiet_hours_end: int | None = Field(None, alias="quietHoursEnd", ge=0, le=23)


# === Comments ===


class CommentCreate(MobileBaseModel):
    text: str = Field(min_length=1, max_length=2000)
    is_internal: bool = Field(False, alias="isInternal")


class CommentMinimal(MobileBaseModel):
    id: str
    text: str
    author: str
    ts: int
    is_internal: bool = Field(False, alias="isInternal")


# === Sync ===


class SyncCheckRequest(MobileBaseModel):
    last_sync: int = Field(alias="lastSync")
    incident_ids: list[str] = Field(default_factory=list, alias="incidentIds")


class SyncCheckResponse(MobileBaseModel):
    has_updates: bool = Field(alias="hasUpdates")
    updated_ids: list[str] = Field(default_factory=list, alias="updatedIds")
    deleted_ids: list[str] = Field(default_factory=list, alias="deletedIds")
    server_ts: int = Field(alias="serverTs")


class MobileError(MobileBaseModel):
    code: str
    message: str
    retry_after: int | None = Field(None, alias="retryAfter")
