"""Slack interaction payload handler for button clicks.

Routes interactive component payloads (block_actions) to the appropriate
handler: action approval/rejection, postmortem generation, memory feedback.
"""

from __future__ import annotations

import json

import structlog

from ..actions.approval import ApprovalWorkflow
from ..actions.executor import ActionExecutor
from .slack_lifecycle import get_slack_client, post_status_update

logger = structlog.get_logger()

_workflow = ApprovalWorkflow()
_executor = ActionExecutor()


async def handle_interaction(payload: dict) -> dict | None:
    """Route a Slack interaction payload to the correct handler.

    Returns a Slack response dict or None.
    """
    payload_type = payload.get("type")
    if payload_type != "block_actions":
        return None

    actions = payload.get("actions") or []
    if not actions:
        return None

    action = actions[0]
    action_id = action.get("action_id", "")
    user = payload.get("user", {})
    user_name = user.get("username") or user.get("name") or user.get("id", "unknown")
    channel = payload.get("channel", {})
    channel_id = channel.get("id", "")

    # Memory feedback actions are handled by SlackAdapter.handle_feedback_interaction
    if action_id.startswith("memory_feedback_"):
        return None  # Let existing handler deal with it

    # Action approval
    if action_id.startswith("action_approve:"):
        return await _handle_action_approval(action, user_name, channel_id, approved=True)

    # Action rejection
    if action_id.startswith("action_reject:"):
        return await _handle_action_approval(action, user_name, channel_id, approved=False)

    # Generate postmortem
    if action_id == "generate_postmortem":
        return await _handle_generate_postmortem(action, user_name, channel_id)

    logger.debug("slack_interaction_unhandled", action_id=action_id)
    return None


async def _handle_action_approval(
    action: dict, user_name: str, channel_id: str, approved: bool
) -> dict:
    """Handle action approve/reject button clicks."""
    value_raw = action.get("value", "{}")
    try:
        value = json.loads(value_raw)
    except json.JSONDecodeError:
        value = {}

    action_item_id = value.get("action_id", "")
    incident_id = value.get("incident_id", "")

    try:
        if approved:
            result = _workflow.approve(action_item_id, user_name)
            verb = "approved"
        else:
            result = _workflow.reject(action_item_id, user_name)
            verb = "rejected"

        logger.info(
            "slack_action_decision",
            action_id=action_item_id,
            incident_id=incident_id,
            decision=verb,
            user=user_name,
        )

        # Execute if approved
        if approved and result:
            try:
                exec_result = await _executor.execute(result)
                status_msg = f"Action `{result.description}` executed successfully."
                if exec_result and hasattr(exec_result, "execution_result"):
                    status_msg += f"\nResult: {json.dumps(exec_result.execution_result or {}, indent=2)[:500]}"
            except Exception as e:
                status_msg = f"Action `{result.description}` execution failed: {e}"
                logger.error("slack_action_execution_failed", error=str(e))
        else:
            status_msg = f"Action `{result.description if result else action_item_id}` {verb} by {user_name}."

        return {
            "response_type": "in_channel",
            "replace_original": False,
            "text": status_msg,
        }

    except KeyError:
        return {
            "response_type": "ephemeral",
            "text": f"Action `{action_item_id}` not found or already processed.",
        }
    except Exception as e:
        logger.error("slack_action_handling_error", error=str(e))
        return {
            "response_type": "ephemeral",
            "text": f"Error processing action: {e}",
        }


async def _handle_generate_postmortem(
    action: dict, user_name: str, channel_id: str
) -> dict:
    """Handle Generate Postmortem button click."""
    incident_id = action.get("value", "")

    try:
        from ..postmortem.generator import PostmortemGenerator

        generator = PostmortemGenerator()
        # Fire-and-forget — post result to channel when done
        import asyncio

        async def _generate_and_post():
            try:
                postmortem = await generator.generate(incident_id)
                client = await get_slack_client(None)
                if client and channel_id:
                    summary = postmortem.get("summary", "Postmortem generated.") if isinstance(postmortem, dict) else str(postmortem)[:2000]
                    await client.chat_postMessage(
                        channel=channel_id,
                        text=f"📋 *Postmortem for {incident_id}*\n{summary}",
                    )
            except Exception as e:
                logger.error("postmortem_generation_failed", incident_id=incident_id, error=str(e))
                client = await get_slack_client(None)
                if client and channel_id:
                    await client.chat_postMessage(
                        channel=channel_id,
                        text=f"❌ Failed to generate postmortem for {incident_id}: {e}",
                    )

        asyncio.create_task(_generate_and_post())

        return {
            "response_type": "ephemeral",
            "text": f"🔄 Generating postmortem for `{incident_id}`... Results will be posted to this channel.",
        }

    except Exception as e:
        logger.error("postmortem_trigger_error", error=str(e))
        return {
            "response_type": "ephemeral",
            "text": f"Error triggering postmortem: {e}",
        }
