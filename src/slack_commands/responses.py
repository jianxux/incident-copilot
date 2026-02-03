"""Slack Block Kit response builders."""
from typing import Any

class BlockKitBuilder:
    @classmethod
    def help_response(cls) -> dict[str, Any]:
        blocks = [{"type": "header", "text": {"type": "plain_text", "text": "Incident Copilot Commands", "emoji": True}},
                  {"type": "section", "text": {"type": "mrkdwn", "text": "• `/incident status` - Show active incidents\n• `/incident search <query>` - Search incidents\n• `/incident recent [n]` - Recent incidents\n• `/incident runbook <service>` - Get runbook\n• `/incident help` - This help"}}]
        return {"response_type": "ephemeral", "blocks": blocks, "text": "Commands"}

    @classmethod
    def status_response(cls, incidents, stats) -> dict[str, Any]:
        total = stats.get("total", 0)
        blocks = [{"type": "header", "text": {"type": "plain_text", "text": "Active Incidents", "emoji": True}}]
        if not incidents:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "_No active incidents._"}})
        return {"response_type": "ephemeral", "blocks": blocks, "text": f"Active: {total}"}

    @classmethod
    def search_response(cls, query, results, total_count=0) -> dict[str, Any]:
        blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Search: {query}", "emoji": True}}]
        if not results:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "_No incidents found._"}})
        return {"response_type": "ephemeral", "blocks": blocks, "text": f"Search: {query}"}

    @classmethod
    def recent_response(cls, incidents, count) -> dict[str, Any]:
        blocks = [{"type": "header", "text": {"type": "plain_text", "text": "Recent Incidents", "emoji": True}}]
        if not incidents:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "_No recent incidents._"}})
        return {"response_type": "ephemeral", "blocks": blocks, "text": "Recent"}

    @classmethod
    def runbook_response(cls, service, runbooks) -> dict[str, Any]:
        blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Runbooks: {service}", "emoji": True}}]
        if not runbooks:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "_No runbooks found._"}})
        return {"response_type": "ephemeral", "blocks": blocks, "text": f"Runbooks: {service}"}

    @classmethod
    def error_response(cls, message, details=None) -> dict[str, Any]:
        text = f"Error: {message}"
        return {"response_type": "ephemeral", "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}], "text": text}

    @classmethod
    def make_public(cls, response) -> dict[str, Any]:
        response = response.copy()
        response["response_type"] = "in_channel"
        return response
