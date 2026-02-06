"""Incident Communication Hub.

Provides multi-channel communication management during incidents:
- Stakeholder management (who needs to know what)
- Communication templates by audience (technical, executive, customer)
- Scheduled update reminders
- Multi-channel delivery (Slack, email, SMS, status page)
- Communication audit trail
"""

from .channels import (
    ChannelDelivery,
    DeliveryResult,
    EmailChannel,
    SlackChannel,
    SMSChannel,
    StatusPageChannel,
    get_channel_delivery,
)
from .models import (
    AudienceType,
    CommunicationAuditEntry,
    CommunicationPlan,
    CommunicationUpdate,
    DeliveryChannel,
    DeliveryStatus,
    ScheduledReminder,
    Stakeholder,
    StakeholderGroup,
    UpdatePriority,
)
from .scheduler import (
    UpdateReminder,
    UpdateScheduler,
    get_update_scheduler,
)
from .templates import (
    CommunicationTemplate,
    TemplateLibrary,
    get_template_library,
)

__all__ = [
    # Models
    "AudienceType",
    "CommunicationAuditEntry",
    "CommunicationPlan",
    "CommunicationUpdate",
    "DeliveryChannel",
    "DeliveryStatus",
    "ScheduledReminder",
    "Stakeholder",
    "StakeholderGroup",
    "UpdatePriority",
    # Templates
    "CommunicationTemplate",
    "TemplateLibrary",
    "get_template_library",
    # Scheduler
    "UpdateReminder",
    "UpdateScheduler",
    "get_update_scheduler",
    # Channels
    "ChannelDelivery",
    "DeliveryResult",
    "EmailChannel",
    "SlackChannel",
    "SMSChannel",
    "StatusPageChannel",
    "get_channel_delivery",
]
