"""Slack Block Kit integration for suggested actions."""

from typing import Any

from .models import ActionStatus, RiskLevel, SuggestedAction

_RISK_EMOJI = {
    RiskLevel.LOW: "🟢",
    RiskLevel.MEDIUM: "🟡",
    RiskLevel.HIGH: "🟠",
    RiskLevel.CRITICAL: "🔴",
}

_STATUS_EMOJI = {
    ActionStatus.SUGGESTED: "💡",
    ActionStatus.PENDING_APPROVAL: "⏳",
    ActionStatus.APPROVED: "✅",
    ActionStatus.REJECTED: "❌",
    ActionStatus.EXECUTING: "⚙️",
    ActionStatus.EXECUTED: "✅",
    ActionStatus.FAILED: "💥",
}


def build_action_buttons(actions: list[SuggestedAction]) -> list[dict[str, Any]]:
    """Create Slack Block Kit blocks with action buttons."""
    blocks: list[dict[str, Any]] = []

    for action in actions:
        risk_emoji = _RISK_EMOJI.get(action.risk_level, "⚪")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{risk_emoji} *{action.action_type.replace('_', ' ').title()}*\n"
                        f"{action.description}\n"
                        f"Risk: {action.risk_level} | "
                        f"{'Approval required' if action.requires_approval else 'Auto-executable'}"
                    ),
                },
            }
        )

        buttons = []
        if action.requires_approval:
            buttons.extend(
                [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve"},
                        "style": "primary",
                        "action_id": f"action_approve_{action.id}",
                        "value": action.id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject"},
                        "style": "danger",
                        "action_id": f"action_reject_{action.id}",
                        "value": action.id,
                    },
                ]
            )
        else:
            buttons.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "▶️ Execute"},
                    "style": "primary",
                    "action_id": f"action_execute_{action.id}",
                    "value": action.id,
                }
            )

        buttons.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "🔍 Dry Run"},
                "action_id": f"action_dryrun_{action.id}",
                "value": action.id,
            }
        )

        blocks.append({"type": "actions", "elements": buttons})

    return blocks


def build_verdict_with_actions(
    verdict: dict[str, Any], actions: list[SuggestedAction]
) -> list[dict[str, Any]]:
    """Build full Slack message combining verdict card with action buttons."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔍 Incident Analysis Complete",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Summary:* {verdict.get('summary', 'N/A')}\n\n"
                    f"*Root Cause:* {verdict.get('root_cause_hypothesis', 'N/A')}\n\n"
                    f"*Confidence:* {verdict.get('confidence', 'N/A')}%"
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"⚡ Suggested Actions ({len(actions)})",
            },
        },
    ]

    blocks.extend(build_action_buttons(actions))
    return blocks


def format_action_result(action: SuggestedAction) -> list[dict[str, Any]]:
    """Format action execution result as Slack blocks."""
    status_emoji = _STATUS_EMOJI.get(action.status, "❓")
    result_text = ""
    if action.execution_result:
        for k, v in action.execution_result.items():
            result_text += f"• *{k}:* {v}\n"

    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{status_emoji} *{action.action_type.replace('_', ' ').title()}* "
                    f"— {action.status.replace('_', ' ').title()}\n"
                    f"{'🧪 _Dry run_ ' if action.dry_run else ''}"
                    f"Target: {action.target_service}\n\n"
                    f"{result_text}"
                ),
            },
        }
    ]
    return blocks
