"""On-Call Provider integrations."""

from .opsgenie import OpsgenieProvider
from .pagerduty import PagerDutyProvider

__all__ = ["PagerDutyProvider", "OpsgenieProvider"]
