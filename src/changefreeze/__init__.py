"""Change Freeze Management system.

This module provides functionality for:
- Defining freeze periods (e.g., holiday freeze, end-of-quarter)
- Per-service or global freezes
- Exception requests with approval workflow
- Detecting GitHub deployments during freeze
- Alerting on violations (Slack, email)
- Audit logging of all freeze violations
- Pre-approved emergency deployment flag
"""

from .models import (
    ApprovalStatus,
    ChangeFreeze,
    DeploymentEvent,
    FreezeException,
    FreezeScope,
    FreezeStatus,
    FreezeViolation,
    ViolationSeverity,
)
from .store import changefreeze_store

__all__ = [
    "ApprovalStatus",
    "ChangeFreeze",
    "DeploymentEvent",
    "FreezeException",
    "FreezeScope",
    "FreezeStatus",
    "FreezeViolation",
    "ViolationSeverity",
    "changefreeze_store",
]
