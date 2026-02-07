"""Notification templates for different incident events."""

from datetime import datetime
from string import Template
from typing import Any

from .models import ChannelType, NotificationType, Severity


class NotificationTemplate:
    """Template for rendering notification messages."""

    def __init__(
        self,
        subject: str,
        body: str,
        html_body: str | None = None,
        slack_blocks: list[dict] | None = None,
    ):
        self.subject = Template(subject)
        self.body = Template(body)
        self.html_body = Template(html_body) if html_body else None
        self.slack_blocks = slack_blocks

    def render(self, **context: Any) -> dict[str, Any]:
        """Render the template with the given context."""
        # Ensure all values are strings for Template substitution
        safe_context = {k: str(v) if v is not None else "" for k, v in context.items()}

        result = {
            "subject": self.subject.safe_substitute(safe_context),
            "body": self.body.safe_substitute(safe_context),
        }

        if self.html_body:
            result["html_body"] = self.html_body.safe_substitute(safe_context)

        if self.slack_blocks:
            result["slack_blocks"] = self._render_slack_blocks(safe_context)

        return result

    def _render_slack_blocks(self, context: dict[str, str]) -> list[dict]:
        """Render Slack blocks with context substitution."""
        import json

        blocks_str = json.dumps(self.slack_blocks)
        for key, value in context.items():
            blocks_str = blocks_str.replace(f"${{{key}}}", value)
            blocks_str = blocks_str.replace(f"${key}", value)
        return json.loads(blocks_str)


# Severity emoji mapping
SEVERITY_EMOJI = {
    Severity.P1: "🔴",
    Severity.P2: "🟠",
    Severity.P3: "🟡",
    Severity.P4: "🔵",
    Severity.P5: "⚪",
}

SEVERITY_COLOR = {
    Severity.P1: "#FF0000",
    Severity.P2: "#FF6600",
    Severity.P3: "#FFCC00",
    Severity.P4: "#0066FF",
    Severity.P5: "#999999",
}


# Default templates for each notification type
DEFAULT_TEMPLATES: dict[NotificationType, NotificationTemplate] = {
    NotificationType.INCIDENT_CREATED: NotificationTemplate(
        subject="[${severity}] New Incident: ${title}",
        body="""
New incident created:

Title: ${title}
Severity: ${severity}
Service: ${service}
Team: ${team}

Description:
${description}

Incident ID: ${incident_id}
Created: ${created_at}

View incident: ${incident_url}
""".strip(),
        html_body="""
<!DOCTYPE html>
<html>
<head><style>
  .container { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; }
  .header { background: ${severity_color}; color: white; padding: 20px; border-radius: 8px 8px 0 0; }
  .body { background: #f5f5f5; padding: 20px; border-radius: 0 0 8px 8px; }
  .label { font-weight: bold; color: #666; }
  .value { margin-bottom: 10px; }
  .btn { background: #0066FF; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; }
</style></head>
<body>
<div class="container">
  <div class="header">
    <h2>${severity_emoji} [${severity}] New Incident</h2>
    <h3>${title}</h3>
  </div>
  <div class="body">
    <p class="label">Service</p>
    <p class="value">${service}</p>
    <p class="label">Team</p>
    <p class="value">${team}</p>
    <p class="label">Description</p>
    <p class="value">${description}</p>
    <p><a href="${incident_url}" class="btn">View Incident</a></p>
  </div>
</div>
</body>
</html>
""".strip(),
        slack_blocks=[
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "${severity_emoji} [${severity}] New Incident",
                },
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": "*${title}*"}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*Service:*\n${service}"},
                    {"type": "mrkdwn", "text": "*Team:*\n${team}"},
                    {"type": "mrkdwn", "text": "*Severity:*\n${severity}"},
                    {"type": "mrkdwn", "text": "*ID:*\n${incident_id}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Description:*\n${description}"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Incident"},
                        "url": "${incident_url}",
                        "style": "primary",
                    }
                ],
            },
        ],
    ),
    NotificationType.BREACH_WARNING: NotificationTemplate(
        subject="⚠️ [${severity}] SLA Breach Warning: ${title}",
        body="""
⚠️ SLA BREACH WARNING

Incident "${title}" is approaching SLA breach!

Current Status: ${status}
Time to Breach: ${time_to_breach}
SLA Target: ${sla_target}

Severity: ${severity}
Service: ${service}
Assigned To: ${assignee}

Incident ID: ${incident_id}

IMMEDIATE ACTION REQUIRED

View incident: ${incident_url}
""".strip(),
        html_body="""
<!DOCTYPE html>
<html>
<head><style>
  .container { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; }
  .header { background: #FF6600; color: white; padding: 20px; border-radius: 8px 8px 0 0; }
  .body { background: #fff3e0; padding: 20px; border-radius: 0 0 8px 8px; }
  .warning { background: #FF6600; color: white; padding: 10px; text-align: center; font-weight: bold; }
  .countdown { font-size: 24px; font-weight: bold; color: #FF0000; text-align: center; padding: 20px; }
  .btn { background: #FF0000; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; }
</style></head>
<body>
<div class="container">
  <div class="header">
    <h2>⚠️ SLA Breach Warning</h2>
    <h3>${title}</h3>
  </div>
  <div class="body">
    <div class="countdown">Time to Breach: ${time_to_breach}</div>
    <p><strong>SLA Target:</strong> ${sla_target}</p>
    <p><strong>Assigned To:</strong> ${assignee}</p>
    <p><strong>Service:</strong> ${service}</p>
    <p style="text-align: center;"><a href="${incident_url}" class="btn">Take Action Now</a></p>
  </div>
</div>
</body>
</html>
""".strip(),
        slack_blocks=[
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚠️ SLA Breach Warning",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*${title}*\n\n🕐 *Time to Breach:* ${time_to_breach}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*SLA Target:*\n${sla_target}"},
                    {"type": "mrkdwn", "text": "*Assignee:*\n${assignee}"},
                    {"type": "mrkdwn", "text": "*Service:*\n${service}"},
                    {"type": "mrkdwn", "text": "*Severity:*\n${severity}"},
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🚨 Take Action Now"},
                        "url": "${incident_url}",
                        "style": "danger",
                    }
                ],
            },
        ],
    ),
    NotificationType.INCIDENT_RESOLVED: NotificationTemplate(
        subject="✅ [${severity}] Resolved: ${title}",
        body="""
✅ INCIDENT RESOLVED

Incident "${title}" has been resolved.

Resolution: ${resolution}
Resolved By: ${resolved_by}
Duration: ${duration}

Severity: ${severity}
Service: ${service}

Incident ID: ${incident_id}
Resolved At: ${resolved_at}

View incident: ${incident_url}
""".strip(),
        html_body="""
<!DOCTYPE html>
<html>
<head><style>
  .container { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; }
  .header { background: #00AA00; color: white; padding: 20px; border-radius: 8px 8px 0 0; }
  .body { background: #e8f5e9; padding: 20px; border-radius: 0 0 8px 8px; }
  .metric { display: inline-block; padding: 10px 20px; background: white; border-radius: 4px; margin: 5px; }
  .btn { background: #0066FF; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; }
</style></head>
<body>
<div class="container">
  <div class="header">
    <h2>✅ Incident Resolved</h2>
    <h3>${title}</h3>
  </div>
  <div class="body">
    <p><strong>Resolution:</strong></p>
    <p>${resolution}</p>
    <div class="metric"><strong>Duration:</strong> ${duration}</div>
    <div class="metric"><strong>Resolved By:</strong> ${resolved_by}</div>
    <p style="text-align: center; margin-top: 20px;"><a href="${incident_url}" class="btn">View Details</a></p>
  </div>
</div>
</body>
</html>
""".strip(),
        slack_blocks=[
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "✅ Incident Resolved",
                    "emoji": True,
                },
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": "*${title}*"}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*Duration:*\n${duration}"},
                    {"type": "mrkdwn", "text": "*Resolved By:*\n${resolved_by}"},
                    {"type": "mrkdwn", "text": "*Service:*\n${service}"},
                    {"type": "mrkdwn", "text": "*Severity:*\n${severity}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Resolution:*\n${resolution}"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Details"},
                        "url": "${incident_url}",
                    }
                ],
            },
        ],
    ),
    NotificationType.ESCALATION: NotificationTemplate(
        subject="🔺 [${severity}] Escalation: ${title}",
        body="""
🔺 INCIDENT ESCALATED

Incident "${title}" has been escalated to you.

Previous Assignee: ${previous_assignee}
Escalation Reason: ${escalation_reason}

Severity: ${severity}
Service: ${service}
Current Status: ${status}

Incident ID: ${incident_id}

View incident: ${incident_url}
""".strip(),
    ),
    NotificationType.ASSIGNMENT: NotificationTemplate(
        subject="📋 [${severity}] Assigned: ${title}",
        body="""
📋 INCIDENT ASSIGNED TO YOU

You have been assigned to incident "${title}".

Severity: ${severity}
Service: ${service}
Current Status: ${status}
SLA Target: ${sla_target}

Description:
${description}

Incident ID: ${incident_id}

View incident: ${incident_url}
""".strip(),
    ),
    NotificationType.DIGEST: NotificationTemplate(
        subject="📊 Incident Digest - ${period}",
        body="""
📊 INCIDENT DIGEST - ${period}

Summary:
- Total Incidents: ${total_incidents}
- Active: ${active_incidents}
- Resolved: ${resolved_incidents}
- P1/P2: ${critical_incidents}

Top Services Affected:
${top_services}

Recent Incidents:
${incident_list}

View Dashboard: ${dashboard_url}
""".strip(),
    ),
}


class TemplateRenderer:
    """Renders notification templates with context."""

    def __init__(self, custom_templates: dict[str, str] | None = None):
        self.custom_templates = custom_templates or {}

    def render(
        self,
        notification_type: NotificationType,
        channel_type: ChannelType,
        **context: Any,
    ) -> dict[str, Any]:
        """Render a notification for the given type and channel."""
        template = DEFAULT_TEMPLATES.get(notification_type)
        if not template:
            return {
                "subject": f"Notification: {notification_type.value}",
                "body": str(context),
            }

        # Add computed context values
        severity = context.get("severity")
        if isinstance(severity, Severity):
            context["severity_emoji"] = SEVERITY_EMOJI.get(severity, "")
            context["severity_color"] = SEVERITY_COLOR.get(severity, "#666666")
        elif isinstance(severity, str):
            sev = (
                Severity(severity)
                if severity in [s.value for s in Severity]
                else Severity.P3
            )
            context["severity_emoji"] = SEVERITY_EMOJI.get(sev, "")
            context["severity_color"] = SEVERITY_COLOR.get(sev, "#666666")

        # Format timestamps
        for key in ["created_at", "resolved_at", "updated_at"]:
            if key in context and isinstance(context[key], datetime):
                context[key] = context[key].strftime("%Y-%m-%d %H:%M:%S UTC")

        # Render template
        rendered = template.render(**context)

        # Apply custom template overrides if present
        template_key = f"{notification_type.value}_{channel_type.value}"
        if template_key in self.custom_templates:
            custom = Template(self.custom_templates[template_key])
            rendered["body"] = custom.safe_substitute(context)

        return rendered

    def render_for_channel(
        self,
        notification_type: NotificationType,
        channel_type: ChannelType,
        **context: Any,
    ) -> dict[str, Any]:
        """Render optimized for a specific channel type."""
        rendered = self.render(notification_type, channel_type, **context)

        if channel_type == ChannelType.SLACK and "slack_blocks" in rendered:
            return {"blocks": rendered["slack_blocks"], "text": rendered["subject"]}

        if channel_type == ChannelType.EMAIL and "html_body" in rendered:
            return {
                "subject": rendered["subject"],
                "text": rendered["body"],
                "html": rendered["html_body"],
            }

        if channel_type == ChannelType.SMS:
            # SMS: Keep it short
            body = rendered["body"]
            if len(body) > 160:
                body = body[:157] + "..."
            return {"text": body}

        if channel_type == ChannelType.PUSH:
            return {
                "title": rendered["subject"][:50],
                "body": rendered["body"][:100],
                "data": context,
            }

        return rendered
