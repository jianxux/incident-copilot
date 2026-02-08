"""Slack Block Kit response builders."""

from typing import Any


class BlockKitBuilder:
    @classmethod
    def help_response(cls) -> dict[str, Any]:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🤖 Incident Copilot Commands",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Incident Management:*\n"
                        "• `/incident status` - Show active incidents\n"
                        "• `/incident search <query>` - Search incidents\n"
                        "• `/incident recent [n]` - Recent incidents\n"
                        "• `/incident runbook <service>` - Get runbook\n\n"
                        "*AI Copilot:*\n"
                        "• `/incident ask <id> <question>` - Ask the AI copilot\n"
                        "• `/incident summarize <id>` - Generate incident summary\n"
                        "• `/incident suggest <id>` - Get AI suggestions\n"
                    ),
                },
            },
        ]
        return {"response_type": "ephemeral", "blocks": blocks, "text": "Commands"}

    @classmethod
    def copilot_response(
        cls, incident_id: str, question: str, answer: str
    ) -> dict[str, Any]:
        blocks = [
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🤖 *Copilot* | Incident: `{incident_id}`",
                    }
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Q:* {question}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": answer[:2900],  # Slack limit
                },
            },
        ]
        return {"response_type": "ephemeral", "blocks": blocks, "text": answer[:100]}

    @classmethod
    def summary_response(cls, incident_id: str, summary: dict) -> dict[str, Any]:
        title = summary.get("title", "Incident Summary")
        summary_text = summary.get("summary", "")
        root_cause = summary.get("root_cause", "Unknown")
        resolution = summary.get("resolution", "Ongoing")
        severity = summary.get("severity_assessment", "")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📋 {title}",
                    "emoji": True,
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Incident: `{incident_id}` | {severity}",
                    }
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": summary_text},
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Root Cause:*\n{root_cause}"},
                    {"type": "mrkdwn", "text": f"*Resolution:*\n{resolution}"},
                ],
            },
        ]

        action_items = summary.get("action_items", [])
        if action_items:
            actions_text = "\n".join(f"• {item}" for item in action_items[:5])
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Action Items:*\n{actions_text}",
                    },
                }
            )

        return {"response_type": "ephemeral", "blocks": blocks, "text": title}

    @classmethod
    def suggestions_response(
        cls, incident_id: str, suggestions: list[str]
    ) -> dict[str, Any]:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "💡 Suggested Next Steps",
                    "emoji": True,
                },
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Incident: `{incident_id}`"}],
            },
        ]

        if suggestions:
            suggestions_text = "\n".join(f"• {s}" for s in suggestions[:5])
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": suggestions_text},
                }
            )
        else:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "_No suggestions available. Add more context first._",
                    },
                }
            )

        return {"response_type": "ephemeral", "blocks": blocks, "text": "Suggestions"}

    @classmethod
    def status_response(cls, incidents, stats) -> dict[str, Any]:
        total = stats.get("total", 0)
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Active Incidents",
                    "emoji": True,
                },
            }
        ]
        if not incidents:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "_No active incidents._"},
                }
            )
        return {
            "response_type": "ephemeral",
            "blocks": blocks,
            "text": f"Active: {total}",
        }

    @classmethod
    def search_response(cls, query, results, total_count=0) -> dict[str, Any]:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Search: {query}",
                    "emoji": True,
                },
            }
        ]
        if not results:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "_No incidents found._"},
                }
            )
        return {
            "response_type": "ephemeral",
            "blocks": blocks,
            "text": f"Search: {query}",
        }

    @classmethod
    def recent_response(cls, incidents, count) -> dict[str, Any]:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Recent Incidents",
                    "emoji": True,
                },
            }
        ]
        if not incidents:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "_No recent incidents._"},
                }
            )
        return {"response_type": "ephemeral", "blocks": blocks, "text": "Recent"}

    @classmethod
    def runbook_response(cls, service, runbooks) -> dict[str, Any]:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Runbooks: {service}",
                    "emoji": True,
                },
            }
        ]
        if not runbooks:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "_No runbooks found._"},
                }
            )
        return {
            "response_type": "ephemeral",
            "blocks": blocks,
            "text": f"Runbooks: {service}",
        }

    @classmethod
    def error_response(cls, message, details=None) -> dict[str, Any]:
        text = f"Error: {message}"
        return {
            "response_type": "ephemeral",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
            "text": text,
        }

    @classmethod
    def make_public(cls, response) -> dict[str, Any]:
        response = response.copy()
        response["response_type"] = "in_channel"
        return response
