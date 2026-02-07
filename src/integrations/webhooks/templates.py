"""Payload templates for webhook events."""

from datetime import datetime
from typing import Any
from uuid import UUID

from .models import WebhookEvent, WebhookEventType


# Built-in templates for each event type
BUILTIN_TEMPLATES: dict[WebhookEventType, dict[str, Any]] = {
    WebhookEventType.INCIDENT_CREATED: {
        "event": "incident.created",
        "data": {
            "incident": {
                "id": "{{incident_id}}",
                "title": "{{title}}",
                "description": "{{description}}",
                "severity": "{{severity}}",
                "status": "{{status}}",
                "created_at": "{{created_at}}",
                "url": "{{incident_url}}"
            },
            "organization": {
                "id": "{{organization_id}}",
                "name": "{{organization_name}}"
            }
        }
    },
    WebhookEventType.INCIDENT_RESOLVED: {
        "event": "incident.resolved",
        "data": {
            "incident": {
                "id": "{{incident_id}}",
                "title": "{{title}}",
                "severity": "{{severity}}",
                "resolved_at": "{{resolved_at}}",
                "resolution_time_minutes": "{{resolution_time_minutes}}",
                "resolved_by": "{{resolved_by}}"
            }
        }
    },
    WebhookEventType.SLA_BREACHED: {
        "event": "sla.breached",
        "data": {
            "incident": {
                "id": "{{incident_id}}",
                "title": "{{title}}",
                "severity": "{{severity}}"
            },
            "sla": {
                "type": "{{sla_type}}",
                "target_minutes": "{{target_minutes}}",
                "actual_minutes": "{{actual_minutes}}",
                "breached_at": "{{breached_at}}"
            }
        }
    },
    WebhookEventType.SLA_WARNING: {
        "event": "sla.warning",
        "data": {
            "incident": {
                "id": "{{incident_id}}",
                "title": "{{title}}"
            },
            "sla": {
                "type": "{{sla_type}}",
                "target_minutes": "{{target_minutes}}",
                "elapsed_minutes": "{{elapsed_minutes}}",
                "warning_threshold_percent": "{{warning_threshold_percent}}"
            }
        }
    },
    WebhookEventType.INCIDENT_ESCALATED: {
        "event": "incident.escalated",
        "data": {
            "incident": {
                "id": "{{incident_id}}",
                "title": "{{title}}",
                "severity": "{{severity}}"
            },
            "escalation": {
                "from_level": "{{from_level}}",
                "to_level": "{{to_level}}",
                "reason": "{{escalation_reason}}",
                "escalated_to": "{{escalated_to}}"
            }
        }
    }
}


class PayloadTemplate:
    """Manages payload templates for webhook events."""
    
    def __init__(self):
        self._custom_templates: dict[str, dict[str, Any]] = {}
    
    def register_template(self, template_id: str, template: dict[str, Any]) -> None:
        """Register a custom template."""
        self._custom_templates[template_id] = template
    
    def get_template(
        self, 
        event_type: WebhookEventType, 
        template_id: str | None = None
    ) -> dict[str, Any]:
        """Get template for event type."""
        if template_id and template_id in self._custom_templates:
            return self._custom_templates[template_id]
        return BUILTIN_TEMPLATES.get(event_type, {"event": event_type.value, "data": {}})
    
    def render(
        self,
        event: WebhookEvent,
        template_id: str | None = None
    ) -> dict[str, Any]:
        """Render event payload using template."""
        template = self.get_template(event.event_type, template_id)
        
        # Build base payload
        payload = {
            "id": str(event.id),
            "type": event.event_type.value,
            "occurred_at": event.occurred_at.isoformat(),
            "source": event.source,
            "version": event.version,
        }
        
        if event.correlation_id:
            payload["correlation_id"] = event.correlation_id
        
        # Merge event data with template structure
        payload["data"] = self._merge_with_template(
            template.get("data", {}), 
            event.payload
        )
        
        return payload
    
    def _merge_with_template(
        self, 
        template: dict[str, Any], 
        data: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge data into template, replacing placeholders."""
        result = {}
        
        for key, value in template.items():
            if isinstance(value, dict):
                result[key] = self._merge_with_template(value, data)
            elif isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                # Extract placeholder key
                placeholder = value[2:-2]
                result[key] = self._get_nested_value(data, placeholder)
            else:
                result[key] = value
        
        # Add any extra data not in template
        for key, value in data.items():
            if key not in result:
                result[key] = self._serialize_value(value)
        
        return result
    
    def _get_nested_value(self, data: dict[str, Any], key: str) -> Any:
        """Get potentially nested value from data."""
        parts = key.split(".")
        value = data
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return self._serialize_value(value)
    
    def _serialize_value(self, value: Any) -> Any:
        """Serialize value for JSON."""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        return value


# Global template manager
template_manager = PayloadTemplate()


def render_webhook_payload(
    event: WebhookEvent,
    template_id: str | None = None
) -> dict[str, Any]:
    """Convenience function to render webhook payload."""
    return template_manager.render(event, template_id)
