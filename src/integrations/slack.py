"""Slack integration adapter."""

import structlog
from slack_sdk.web.async_client import AsyncWebClient

from ..config import Settings
from ..copilot.thread_registry import thread_registry
from ..models import ContextCard

logger = structlog.get_logger()


class SlackAdapter:
    """Adapter for Slack API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            AsyncWebClient(token=settings.slack_bot_token)
            if settings.slack_bot_token
            else None
        )
        self.default_channel = settings.slack_default_channel

    async def send_context_card(
        self, card: ContextCard, channel: str | None = None
    ) -> bool:
        """Send a context card to Slack."""
        if not self.client:
            logger.warning("slack_not_configured")
            return False

        target_channel = channel or self.default_channel

        try:
            blocks = self._build_blocks(card)

            response = await self.client.chat_postMessage(
                channel=target_channel,
                text=f"🚨 Incident: {card.title}",  # Fallback text
                blocks=blocks,
                unfurl_links=False,
            )

            thread_ts = response.get("ts")
            channel_id = response.get("channel") or target_channel
            if thread_ts and channel_id:
                # Team ID is not available in this response; register wildcard mapping.
                await thread_registry.register_thread(
                    team_id="*",
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    incident_id=card.incident_id,
                )

            logger.info(
                "slack_message_sent", channel=target_channel, incident=card.incident_id
            )
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

        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {card.service_name}: {card.title[:100]}",
                    "emoji": True,
                },
            }
        )

        # Alert info
        alert_info = f"*Severity:* {card.severity.value.upper()}  |  *Triggered:* <!date^{int(card.triggered_at.timestamp())}^{{time}}|{card.triggered_at.isoformat()}>"
        if card.alert_url:
            alert_info += f"  |  <{card.alert_url}|View in PagerDuty>"

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": alert_info},
            }
        )

        # ═══ AI VERDICT — the hero block ═══
        if card.verdict:
            confidence_indicator = {
                "high": "🟢 HIGH CONFIDENCE",
                "medium": "🟡 MEDIUM CONFIDENCE",
                "low": "🔴 LOW CONFIDENCE",
            }
            conf = confidence_indicator.get(card.verdict.confidence.value, "⚪ UNKNOWN")

            verdict_text = (
                f"*🎯 VERDICT:* {card.verdict.most_likely_cause}\n"
                f"_{conf}_  •  {card.verdict.evidence}\n\n"
                f"*▶️ DO NOW:* {card.verdict.recommended_action}"
            )
            if card.verdict.secondary_action:
                verdict_text += f"\n*▶️ THEN:* {card.verdict.secondary_action}"

            if card.verdict.deploy_correlated and card.verdict.suspect_deploy:
                verdict_text += f"\n\n⚠️ _Deploy-correlated — suspect commit: `{card.verdict.suspect_deploy}`_"

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": verdict_text},
                }
            )
            blocks.append({"type": "divider"})

        blocks.append({"type": "divider"})

        # Recent Deployments
        if card.github and card.github.recent_deploys:
            deploy_lines = ["*🚀 Recent Deployments:*"]
            for deploy in card.github.recent_deploys[:3]:
                f"<!date^{int(deploy.timestamp.timestamp())}^{{time}}|{deploy.timestamp.isoformat()}>"
                line = f"• `{deploy.short_sha}` by {deploy.author} - _{deploy.message[:60]}_"
                if deploy.url:
                    line = f"• <{deploy.url}|`{deploy.short_sha}`> by {deploy.author} - _{deploy.message[:60]}_"
                deploy_lines.append(line)

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(deploy_lines)},
                }
            )

        # Log Summary (AI or basic)
        if card.ai_summary:
            summary_lines = ["*📋 Top Issues (AI Analysis):*"]
            for issue in card.ai_summary.top_issues[:5]:
                summary_lines.append(f"• {issue}")
            if card.ai_summary.explanation:
                summary_lines.append(f"\n_{card.ai_summary.explanation[:200]}_")

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(summary_lines)},
                }
            )

        elif card.datadog and card.datadog.log_summaries:
            summary_lines = ["*📋 Top Error Patterns:*"]
            for summary in card.datadog.log_summaries[:5]:
                summary_lines.append(f"• ({summary.count}x) {summary.pattern[:80]}")

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(summary_lines)},
                }
            )

        # Similar Past Incidents
        if card.similar_incidents:
            incident_lines = ["*🔄 Similar Past Incidents:*"]
            for inc in card.similar_incidents[:3]:
                line = f"• *{inc.title[:50]}* ({inc.occurred_at.strftime('%Y-%m-%d')})"
                if inc.resolution:
                    line += f"\n  _Resolution: {inc.resolution[:100]}_"
                incident_lines.append(line)

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(incident_lines)},
                }
            )

        # On-Call Information
        if card.oncall and card.oncall.has_oncall:
            oncall_lines = ["*👤 On-Call:*"]
            for person in card.oncall.oncall_persons[:3]:
                mention = person.slack_mention
                oncall_lines.append(f"• {mention}")
            if card.oncall.schedule_url:
                oncall_lines.append(f"<{card.oncall.schedule_url}|View Schedule>")

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(oncall_lines)},
                }
            )

        blocks.append({"type": "divider"})

        # Footer: Owners, Runbook, Dashboard
        footer_parts = []

        if card.oncall and card.oncall.primary_oncall:
            footer_parts.append(
                f"*On-Call:* {card.oncall.primary_oncall.slack_mention}"
            )
        elif card.owners:
            footer_parts.append(f"*Owners:* {', '.join(card.owners[:5])}")
        if card.runbook_url:
            footer_parts.append(f"<{card.runbook_url}|📖 Runbook>")
        if card.dashboard_url:
            footer_parts.append(f"<{card.dashboard_url}|📊 Dashboard>")

        if footer_parts:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": "  |  ".join(footer_parts)}
                    ],
                }
            )

        # Latency metrics — show the North Star
        if card.latency_report and card.latency_report.total_ms is not None:
            budget_emoji = "✅" if card.latency_report.within_budget else "⚠️"
            latency_text = (
                f"{budget_emoji} _Context assembled in "
                f"*{card.latency_report.total_ms}ms* "
                f"(budget: {card.latency_report.budget_ms}ms)_"
            )
            if card.latency_report.alert_to_delivery_ms is not None:
                latency_text += (
                    f"  •  _Alert→Card: "
                    f"{card.latency_report.alert_to_delivery_ms}ms_"
                )
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": latency_text}],
                }
            )
        elif card.assembly_time_ms:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"_Context assembled in {card.assembly_time_ms}ms_",
                        }
                    ],
                }
            )

        return blocks
