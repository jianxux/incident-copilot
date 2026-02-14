"""Slack integration adapter."""

import json

import structlog
from slack_sdk.web.async_client import AsyncWebClient

from ..config import Settings
from ..copilot.thread_registry import thread_registry
from ..memory.feedback import FeedbackStore, ResolutionFeedback
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
        """Build self-contained Slack Block Kit blocks.

        Layout philosophy (Jobs-style "Instant Clarity"):
        1. HEADER — what's on fire
        2. VERDICT — what's wrong and what to do (the hero)
        3. KEY DATA POINTS — 3 most relevant facts (deploy, error spike, similar)
        4. SIMILAR INCIDENTS — the "aha" moment (if available)
        5. RUNBOOK STEPS — inline steps, not links
        6. EXPANDABLE DETAILS — everything else for deep-divers
        7. FOOTER — on-call, links, latency

        An engineer at 3am should never need to click anything.
        """
        blocks: list[dict] = []

        # ─── 1. HEADER ───
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

        # Compact alert metadata line
        alert_parts = [f"*{card.severity.value.upper()}*"]
        ts = int(card.triggered_at.timestamp())
        alert_parts.append(f"<!date^{ts}^{{time}}|{card.triggered_at.isoformat()}>")
        if card.oncall and card.oncall.primary_oncall:
            alert_parts.append(f"👤 {card.oncall.primary_oncall.slack_mention}")
        if card.alert_url:
            alert_parts.append(f"<{card.alert_url}|View Alert>")
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "  |  ".join(alert_parts)}],
            }
        )

        # ─── 2. VERDICT (hero block) ───
        if card.verdict:
            confidence_indicator = {
                "high": "🟢 HIGH",
                "medium": "🟡 MEDIUM",
                "low": "🔴 LOW",
            }
            conf = confidence_indicator.get(card.verdict.confidence.value, "⚪")

            verdict_lines = [
                f"*🎯 {card.verdict.most_likely_cause}*",
                f"_{conf} CONFIDENCE — {card.verdict.evidence}_",
                "",
                f"▶️  *{card.verdict.recommended_action}*",
            ]
            if card.verdict.secondary_action:
                verdict_lines.append(f"▶️  {card.verdict.secondary_action}")
            if card.verdict.deploy_correlated and card.verdict.suspect_deploy:
                verdict_lines.append(
                    f"\n⚠️ _Suspect deploy: `{card.verdict.suspect_deploy}`_"
                )

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(verdict_lines),
                    },
                }
            )
        blocks.append({"type": "divider"})

        # ─── 3. KEY DATA POINTS (3 most relevant facts) ───
        data_points: list[str] = []

        # Fact 1: Last deploy
        deploys = []
        if card.github and card.github.recent_deploys:
            deploys = card.github.recent_deploys
        elif card.gitlab and card.gitlab.recent_deploys:
            deploys = card.gitlab.recent_deploys

        if deploys:
            d = deploys[0]
            deploy_link = f"<{d.url}|`{d.short_sha}`>" if d.url else f"`{d.short_sha}`"
            data_points.append(
                f"🚀 *Last deploy:* {deploy_link} by {d.author} — _{d.message[:50]}_"
            )

        # Fact 2: Error rate / metrics
        if card.datadog and card.datadog.metrics:
            m = card.datadog.metrics
            if m.error_rate is not None:
                rate_str = f"{m.error_rate:.1%}"
                if m.error_rate_baseline is not None:
                    rate_str += f" (baseline: {m.error_rate_baseline:.1%})"
                data_points.append(f"📈 *Error rate:* {rate_str}")
            if m.latency_p99_ms is not None:
                data_points.append(f"⏱️ *P99 latency:* {m.latency_p99_ms:.0f}ms")

        # Fact 3: Blast radius
        if card.topology and card.topology.blast_radius_count > 0:
            affected = card.topology.blast_radius_count
            critical = card.topology.critical_services_affected
            blast_str = f"💥 *Blast radius:* {affected} services affected"
            if critical:
                blast_str += f" (critical: {', '.join(critical[:3])})"
            data_points.append(blast_str)

        if data_points:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(data_points[:3]),
                    },
                }
            )

        # ─── 4. SIMILAR PAST INCIDENTS (the "aha" moment) ───
        if card.similar_incidents:
            sim_lines = ["*🔄 This looks familiar:*"]
            feedback_targets: list[str] = []
            for inc in card.similar_incidents[:3]:
                score = (
                    f" ({inc.similarity_score:.0f}% match)"
                    if inc.similarity_score is not None
                    else ""
                )
                severity = f"[{inc.severity.upper()}] " if inc.severity else ""
                sim_lines.append(
                    f"• {severity}*{inc.title[:60]}*{score} — {inc.occurred_at.strftime('%b %d, %Y')}"
                )
                feedback_targets.append(inc.incident_id)
                if inc.root_cause:
                    sim_lines.append(f"  _Root cause: {inc.root_cause[:80]}_")
                if inc.resolution:
                    sim_lines.append(f"  _✅ Fixed by: {inc.resolution[:80]}_")

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(sim_lines),
                    },
                }
            )
            for recalled_incident_id in feedback_targets:
                blocks.append(
                    self._feedback_actions_block(
                        incident_id=card.incident_id,
                        recalled_incident_id=recalled_incident_id,
                    )
                )

        # ─── 5. INLINE RUNBOOK STEPS ───
        if card.runbook_steps:
            step_lines = ["*📖 First steps from runbook:*"]
            for i, step in enumerate(card.runbook_steps[:3], 1):
                step_lines.append(f"{i}. {step}")

            # Add link to full runbook if available
            if card.runbooks:
                top_rb = card.runbooks[0]
                step_lines.append(f"\n<{top_rb.url}|View full runbook →>")

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(step_lines),
                    },
                }
            )
        elif card.runbooks:
            # Fallback: show runbook links if we couldn't extract steps
            rb_lines = ["*📖 Runbooks:*"]
            for rb in card.runbooks[:3]:
                rb_lines.append(f"• <{rb.url}|{rb.title}>")
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(rb_lines)},
                }
            )

        blocks.append({"type": "divider"})

        # ─── 6. EXPANDABLE DETAILS (for deep-divers) ───
        # Additional deploys beyond the first
        if len(deploys) > 1:
            more_deploys = ["*More recent deploys:*"]
            for d in deploys[1:3]:
                link = f"<{d.url}|`{d.short_sha}`>" if d.url else f"`{d.short_sha}`"
                more_deploys.append(f"• {link} by {d.author} — _{d.message[:50]}_")
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "\n".join(more_deploys)}],
                }
            )

        # Top error patterns (compact)
        if card.ai_summary and card.ai_summary.top_issues:
            issues = card.ai_summary.top_issues[:3]
            issue_text = "*Top errors:* " + " · ".join(
                f"_{iss[:40]}_" for iss in issues
            )
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": issue_text}],
                }
            )
        elif card.datadog and card.datadog.log_summaries:
            patterns = card.datadog.log_summaries[:3]
            pattern_text = "*Top errors:* " + " · ".join(
                f"_{p.pattern[:30]}_ ({p.count}x)" for p in patterns
            )
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": pattern_text}],
                }
            )

        # On-call roster (if multiple people)
        if card.oncall and len(card.oncall.oncall_persons) > 1:
            oncall_text = "*On-call team:* " + ", ".join(
                p.slack_mention for p in card.oncall.oncall_persons[:5]
            )
            if card.oncall.schedule_url:
                oncall_text += f"  |  <{card.oncall.schedule_url}|Schedule>"
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": oncall_text}],
                }
            )

        # ─── 7. FOOTER ───
        footer_parts = []
        if card.owners:
            footer_parts.append(f"Owners: {', '.join(card.owners[:3])}")
        if card.dashboard_url:
            footer_parts.append(f"<{card.dashboard_url}|📊 Dashboard>")

        # Latency metrics
        if card.latency_report and card.latency_report.total_ms is not None:
            budget_emoji = "✅" if card.latency_report.within_budget else "⚠️"
            footer_parts.append(f"{budget_emoji} {card.latency_report.total_ms}ms")
        elif card.assembly_time_ms:
            footer_parts.append(f"⚡ {card.assembly_time_ms}ms")

        if footer_parts:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": "  |  ".join(footer_parts)}
                    ],
                }
            )

        return blocks

    def _feedback_actions_block(
        self,
        incident_id: str,
        recalled_incident_id: str,
    ) -> dict:
        """Build feedback action buttons for one recalled incident."""
        value = json.dumps(
            {
                "incident_id": incident_id,
                "recalled_incident_id": recalled_incident_id,
            }
        )
        return {
            "type": "actions",
            "block_id": f"memory_feedback:{incident_id}:{recalled_incident_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👍 Helpful", "emoji": True},
                    "action_id": "memory_feedback_helpful",
                    "value": value,
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "👎 Not helpful",
                        "emoji": True,
                    },
                    "action_id": "memory_feedback_not_helpful",
                    "value": value,
                    "style": "danger",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📝 Partial", "emoji": True},
                    "action_id": "memory_feedback_partial",
                    "value": value,
                },
            ],
        }

    async def handle_feedback_interaction(
        self,
        payload: dict,
        feedback_store: FeedbackStore,
    ) -> bool:
        """Parse Slack block action payload and persist incident memory feedback."""
        actions = payload.get("actions") or []
        if not actions:
            return False

        action = actions[0]
        action_id = str(action.get("action_id") or "")
        if not action_id.startswith("memory_feedback_"):
            return False

        feedback_value = action_id.replace("memory_feedback_", "", 1)
        if feedback_value not in {"helpful", "not_helpful", "partial"}:
            return False

        value_raw = action.get("value")
        incident_id = ""
        recalled_incident_id = ""
        if isinstance(value_raw, str) and value_raw:
            try:
                parsed = json.loads(value_raw)
                incident_id = str(parsed.get("incident_id") or "")
                recalled_incident_id = str(parsed.get("recalled_incident_id") or "")
            except json.JSONDecodeError:
                incident_id = ""
                recalled_incident_id = ""

        if not incident_id or not recalled_incident_id:
            block_id = str(
                action.get("block_id")
                or payload.get("container", {}).get("block_id")
                or ""
            )
            if block_id.startswith("memory_feedback:"):
                parts = block_id.split(":", 2)
                if len(parts) == 3:
                    incident_id = incident_id or parts[1]
                    recalled_incident_id = recalled_incident_id or parts[2]

        if not incident_id or not recalled_incident_id:
            logger.warning("slack_memory_feedback_missing_ids")
            return False

        await feedback_store.submit(
            ResolutionFeedback(
                incident_id=incident_id,
                recalled_incident_id=recalled_incident_id,
                feedback=feedback_value,  # type: ignore[arg-type]
            )
        )
        logger.info(
            "slack_memory_feedback_stored",
            incident_id=incident_id,
            recalled_incident_id=recalled_incident_id,
            feedback=feedback_value,
        )
        return True
