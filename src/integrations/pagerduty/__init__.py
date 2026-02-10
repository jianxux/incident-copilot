"""PagerDuty integration.

This package contains the newer PagerDuty REST client + models.

Note: the codebase also contains a legacy webhook adapter implementation in
`src/integrations/pagerduty_legacy.py`. A number of internal modules/tests still
import `PagerDutyAdapter` from this package path, so we re-export it here for
backwards-compatibility.
"""

from __future__ import annotations

from ..pagerduty_legacy import PagerDutyAdapter
from .client import PagerDutyClient
from .models import (
    PagerDutyConfig,
    PDEscalationPolicy,
    PDIncident,
    PDOnCall,
    PDSchedule,
    PDService,
    PDUser,
    PDWebhookEvent,
)

__all__ = [
    # Legacy adapter (webhook parsing)
    "PagerDutyAdapter",
    # Client
    "PagerDutyClient",
    # Models
    "PagerDutyConfig",
    "PDEscalationPolicy",
    "PDIncident",
    "PDOnCall",
    "PDSchedule",
    "PDService",
    "PDUser",
    "PDWebhookEvent",
]
