"""Slack integration adapter."""

import structlog
from slack_sdk.web.async_client import AsyncWebClient

from ..config import Settings
from ..models import ContextCard

logger = structlog.get_logger()


class SlackAdapter:
    """Adapter for Slack API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncWebClient(token=settings.slack_bot_token) if settings.slack_bot_token else None
        self.default_channel = settings.slack_default_channel

    async def send_context_card(self, card: ContextCard, channel: str | None = None) -> bool:
        """Send a context card to Slack."""
        if not self.client:
            logger.warning("slack_not_configured")
            return False

        target_channel = channel or self.default_channel

        try:
            blocks = self._build_blocks(card)

            await self.client.chat_postMessage(
                channel=target_channel,
                text=f"🚨 Incident: {card.title}",  # Fallback text
                blocks=blocks,
                unfurl_links=False,
            )

            logger.info("slack_message_sent", channel=target_channel, incident=card.incident_id)
            return True

        except Exception as e:
            logger.error("slack_send_failed", error=str(e))
            return False

    def _build_blocks(self, card: ContextCard) -> list[dict]:
        """Build Slack Block Kit blocks from context card."""
        blocks = []

        # Header
        severity_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "🔵",
        }
        emoji = severity_emoji.get(card.severity.value, "⚪")

        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {card.service_name}: {card.title[:100]}",
                "emoji": True,
            },
        })

        # Alert info
        alert_info = f"*Severity:* {card.severity.value.upper()}  |  *Triggered:* <!date^{int(card.triggered_at.timestamp())}^{{time}}|{card.triggered_at.isoformat()}>"
        if card.alert_url:
            alert_info += f"  |  <{card.alert_url}|View in PagerDuty>"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": alert_info},
        })

        blocks.append({"type": "divider"})

        # Recent Deployments
        if card.github and card.github.recent_deploys:
            deploy_lines = ["*🚀 Recent Deployments:*"]
            for deploy in card.github.recent_deploys[:3]:
                time_str = f"<!date^{int(deploy.timestamp.timestamp())}^{{time}}|{deploy.timestamp.isoformat()}>"
                line = f"• `{deploy.short_sha}` by {deploy.author} - _{deploy.message[:60]}_"
                if deploy.url:
                    line = f"• <{deploy.url}|`{deploy.short_sha}`> by {deploy.author} - _{deploy.message[:60]}_"
                deploy_lines.append(line)

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(deploy_lines)},
            })

        # Log Summary (AI or basic)
        if card.ai_summary:
            summary_lines = ["*📋 Top Issues (AI Analysis):*"]
            for issue in card.ai_summary.top_issues[:5]:
                summary_lines.append(f"• {issue}")
            if card.ai_summary.explanation:
                summary_lines.append(f"\n_{card.ai_summary.explanation[:200]}_")

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(summary_lines)},
            })

        elif card.datadog and card.datadog.log_summaries:
            summary_lines = ["*📋 Top Error Patterns:*"]
            for summary in card.datadog.log_summaries[:5]:
                summary_lines.append(f"• ({summary.count}x) {summary.pattern[:80]}")

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(summary_lines)},
            })

        # Similar Past Incidents
        if card.similar_incidents:
            incident_lines = ["*🔄 Similar Past Incidents:*"]
            for inc in card.similar_incidents[:3]:
                line = f"• *{inc.title[:50]}* ({inc.occurred_at.strftime('%Y-%m-%d')})"
                if inc.resolution:
                    line += f"\n  _Resolution: {inc.resolution[:100]}_"
                incident_lines.append(line)

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(incident_lines)},
            })

        blocks.append({"type": "divider"})

        # Footer: Owners, Runbook, Dashboard
        footer_parts = []

        if card.owners:
            footer_parts.append(f"*Owners:* {', '.join(card.owners[:5])}")
        if card.runbook_url:
            footer_parts.append(f"<{card.runbook_url}|📖 Runbook>")
        if card.dashboard_url:
            footer_parts.append(f"<{card.dashboard_url}|📊 Dashboard>")

        if footer_parts:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "  |  ".join(footer_parts)}],
            })

        # Assembly time
        if card.assembly_time_ms:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"_Context assembled in {card.assembly_time_ms}ms_"}
                ],
            })

        return blocks
