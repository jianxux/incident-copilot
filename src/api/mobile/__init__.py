"""Mobile API module for incident-copilot."""

from .models import (
    BiometricAuthRequest,
    BulkActionRequest,
    BulkActionResponse,
    CommentCreate,
    CommentMinimal,
    DashboardSummary,
    DeviceRegistration,
    DeviceRegistrationResponse,
    IncidentCompact,
    IncidentFull,
    IncidentListResponse,
    IncidentMinimal,
    IncidentStatus,
    MobileError,
    NotificationPreferences,
    PaginationMeta,
    Platform,
    QuickActionRequest,
    QuickActionResponse,
    QuickActionType,
    Severity,
    SeverityCount,
    SyncCheckRequest,
    SyncCheckResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
)
from .push import (
    DeviceTokenStore,
    PushConfig,
    PushPayload,
    PushResult,
    PushService,
    PushStatus,
    get_push_service,
)
from .routes import router

__all__ = [
    "router",
    # Enums
    "Severity",
    "IncidentStatus",
    "Platform",
    "QuickActionType",
    # Incidents
    "IncidentMinimal",
    "IncidentCompact",
    "IncidentFull",
    "IncidentListResponse",
    "PaginationMeta",
    # Actions
    "QuickActionRequest",
    "QuickActionResponse",
    "BulkActionRequest",
    "BulkActionResponse",
    # Dashboard
    "DashboardSummary",
    "SeverityCount",
    # Auth
    "TokenRefreshRequest",
    "TokenRefreshResponse",
    "BiometricAuthRequest",
    # Push
    "DeviceRegistration",
    "DeviceRegistrationResponse",
    "NotificationPreferences",
    "PushConfig",
    "PushPayload",
    "PushResult",
    "PushStatus",
    "PushService",
    "DeviceTokenStore",
    "get_push_service",
    # Comments
    "CommentCreate",
    "CommentMinimal",
    # Sync
    "SyncCheckRequest",
    "SyncCheckResponse",
    "MobileError",
]
