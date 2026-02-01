"""Microsoft Teams integration adapter using Incoming Webhooks."""

import httpx
import structlog

from ..config import Settings
from ..models import ContextCard

logger = structlog.get_logger()


class TeamsAdapter:
    """Adapter for Microsoft Teams Incoming Webhooks."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.webhook_url = settings.teams_webhook_url

    async def send_context_card(
        self, card: ContextCard, webhook_url: str | None = None
    ) -> bool:
        """Send a context card to Teams via Incoming Webhook."""
        target_url = webhook_url or self.webhook_url

        if not target_url:
            logger.warning("teams_not_configured")
            return False

        try:
            adaptive_card = self._build_adaptive_card(card)

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    target_url,
                    json=adaptive_card,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

            logger.info("teams_message_sent", incident=card.incident_id)
            return True

        except httpx.HTTPStatusError as e:
            logger.error(
                "teams_send_failed", status=e.response.status_code, error=str(e)
            )
            return False
        except Exception as e:
            logger.error("teams_send_failed", error=str(e))
            return False

    def _build_adaptive_card(self, card: ContextCard) -> dict:
        """Build Microsoft Teams Adaptive Card from context card."""
        # Severity color mapping
        severity_colors = {
            "critical": "attention",  # Red
            "high": "warning",  # Orange/Yellow
            "medium": "accent",  # Blue
            "low": "good",  # Green
            "info": "default",  # Gray
        }

        severity_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "🔵",
        }

        emoji = severity_emoji.get(card.severity.value, "⚪")
        color = severity_colors.get(card.severity.value, "default")

        # Build card body
        body = []

        # Header with incident title
        body.append(
            {
                "type": "TextBlock",
                "size": "Large",
                "weight": "Bolder",
                "text": f"{emoji} {card.service_name}: {card.title[:100]}",
                "wrap": True,
                "color": color,
            }
        )

        # Alert info row
        triggered_time = card.triggered_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        body.append(
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"**Severity:** {card.severity.value.upper()}",
                                "wrap": True,
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"**Triggered:** {triggered_time}",
                                "wrap": True,
                            }
                        ],
                    },
                ],
            }
        )

        # Divider
        body.append(
            {
                "type": "TextBlock",
                "text": "─" * 40,
                "wrap": True,
                "spacing": "Small",
            }
        )

        # Recent Deployments section
        if card.github and card.github.recent_deploys:
            deploy_items = ["**🚀 Recent Deployments:**"]
            for deploy in card.github.recent_deploys[:3]:
                time_str = deploy.timestamp.strftime("%H:%M")
                msg = (
                    deploy.message[:60] + "..."
                    if len(deploy.message) > 60
                    else deploy.message
                )
                deploy_items.append(
                    f"• `{deploy.short_sha}` by {deploy.author} - _{msg}_ ({time_str})"
                )

            body.append(
                {
                    "type": "TextBlock",
                    "text": "\n".join(deploy_items),
                    "wrap": True,
                    "spacing": "Medium",
                }
            )

        # Log Summary section (AI or basic)
        if card.ai_summary:
            summary_lines = ["**📋 Top Issues (AI Analysis):**"]
            for issue in card.ai_summary.top_issues[:5]:
                summary_lines.append(f"• {issue}")
            if card.ai_summary.explanation:
                explanation = card.ai_summary.explanation[:200]
                if len(card.ai_summary.explanation) > 200:
                    explanation += "..."
                summary_lines.append(f"\n_{explanation}_")

            body.append(
                {
                    "type": "TextBlock",
                    "text": "\n".join(summary_lines),
                    "wrap": True,
                    "spacing": "Medium",
                }
            )
        elif card.datadog and card.datadog.log_summaries:
            summary_lines = ["**📋 Top Error Patterns:**"]
            for summary in card.datadog.log_summaries[:5]:
                pattern = summary.pattern[:80]
                if len(summary.pattern) > 80:
                    pattern += "..."
                summary_lines.append(f"• ({summary.count}x) {pattern}")

            body.append(
                {
                    "type": "TextBlock",
                    "text": "\n".join(summary_lines),
                    "wrap": True,
                    "spacing": "Medium",
                }
            )

        # Similar Past Incidents section
        if card.similar_incidents:
            incident_lines = ["**🔄 Similar Past Incidents:**"]
            for inc in card.similar_incidents[:3]:
                title = inc.title[:50] + "..." if len(inc.title) > 50 else inc.title
                line = f"• **{title}** ({inc.occurred_at.strftime('%Y-%m-%d')})"
                if inc.resolution:
                    resolution = inc.resolution[:100]
                    if len(inc.resolution) > 100:
                        resolution += "..."
                    line += f"\n  _Resolution: {resolution}_"
                incident_lines.append(line)

            body.append(
                {
                    "type": "TextBlock",
                    "text": "\n".join(incident_lines),
                    "wrap": True,
                    "spacing": "Medium",
                }
            )

        # Divider before footer
        body.append(
            {
                "type": "TextBlock",
                "text": "─" * 40,
                "wrap": True,
                "spacing": "Small",
            }
        )

        # Owners section
        if card.owners:
            owners_text = f"**Owners:** {', '.join(card.owners[:5])}"
            body.append(
                {
                    "type": "TextBlock",
                    "text": owners_text,
                    "wrap": True,
                    "spacing": "Small",
                }
            )

        # Assembly time footer
        if card.assembly_time_ms:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"_Context assembled in {card.assembly_time_ms}ms_",
                    "wrap": True,
                    "size": "Small",
                    "isSubtle": True,
                    "spacing": "Small",
                }
            )

        # Build action buttons
        actions = []

        if card.alert_url:
            actions.append(
                {
                    "type": "Action.OpenUrl",
                    "title": "View in PagerDuty",
                    "url": card.alert_url,
                }
            )

        if card.runbook_url:
            actions.append(
                {
                    "type": "Action.OpenUrl",
                    "title": "📖 View Runbook",
                    "url": card.runbook_url,
                }
            )
        elif card.runbooks:
            # Use first runbook from the list
            actions.append(
                {
                    "type": "Action.OpenUrl",
                    "title": "📖 View Runbook",
                    "url": card.runbooks[0].url,
                }
            )

        if card.dashboard_url:
            actions.append(
                {
                    "type": "Action.OpenUrl",
                    "title": "📊 Open Dashboard",
                    "url": card.dashboard_url,
                }
            )

        # Construct the full Adaptive Card message
        adaptive_card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": body,
                        "actions": actions,
                    },
                }
            ],
        }

        return adaptive_card
