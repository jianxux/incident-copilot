"""
Mobile API module for incident-copilot.

Provides lightweight, bandwidth-optimized endpoints for mobile clients
with push notification support and offline-first patterns.
"""

from .models import (
    # Enums
    Severity,
    IncidentStatus,
    Platform,
    QuickActionType,
    # Incident models
    IncidentMinimal,
    IncidentCompact,
    IncidentFull,
    IncidentListResponse,
    # Pagination
    PaginationMeta,
    # Actions
    QuickActionRequest,
    QuickActionResponse,
    BulkActionRequest,
    BulkActionResponse,
    # Dashboard
    DashboardSummary,
    SeverityCount,
    # Auth
    TokenRefreshRequest,
    TokenRefreshResponse,
    BiometricAuthRequest,
    # Push
    DeviceRegistration,
    DeviceRegistrationResponse,
    NotificationPreferences,
    # Comments
    CommentCreate,
    CommentMinimal,
    # Sync
    SyncCheckRequest,
    SyncCheckResponse,
    # Errors
    MobileError,
)

from .push import (
    PushConfig,
    PushPayload,
    PushResult,
    PushStatus,
    PushService,
    DeviceTokenStore,
    FCMProvider,
    APNSProvider,
    get_push_service,
)

from .routes import router

__all__ = [
    # Router
    "router",
    # Enums
    "Severity",
    "IncidentStatus",
    "Platform",
    "QuickActionType",
    # Incident models
    "IncidentMinimal",
    "IncidentCompact",
    "IncidentFull",
    "IncidentListResponse",
    # Pagination
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
    "FCMProvider",
    "APNSProvider",
    "get_push_service",
    # Comments
    "CommentCreate",
    "CommentMinimal",
    # Sync
    "SyncCheckRequest",
    "SyncCheckResponse",
    # Errors
    "MobileError",
]

__version__ = "1.0.0"
