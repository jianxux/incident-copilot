"""Command handlers for Slack slash commands."""

import re
from dataclasses import dataclass
from typing import Any

import structlog

from ..ai import AICopilot
from ..config import get_settings
from ..runbooks import RunbookLinker
from ..web.store import incident_store
from .responses import BlockKitBuilder

logger = structlog.get_logger()

# Singleton copilot for Slack commands
_slack_copilot: AICopilot | None = None


def get_slack_copilot() -> AICopilot:
    """Get or create the Slack copilot singleton."""
    global _slack_copilot
    if _slack_copilot is None:
        settings = get_settings()
        _slack_copilot = AICopilot(settings)
    return _slack_copilot


@dataclass
class CommandContext:
    user_id: str
    channel_id: str
    team_id: str
    command: str
    text: str
    response_url: str
    public: bool = False


class CommandHandler:
    COMMAND_PATTERN = re.compile(r"^(\w+)(?:\s+(.*))?$")

    def __init__(self):
        self.runbook_linker = RunbookLinker()

    async def handle(self, ctx: CommandContext) -> dict[str, Any]:
        text = ctx.text.strip() if ctx.text else ""
        if text.endswith("--public"):
            ctx.public = True
            text = text[:-8].strip()
        if not text:
            return await self._handle_help(ctx)
        match = self.COMMAND_PATTERN.match(text)
        if not match:
            return BlockKitBuilder.error_response(
                "Invalid command", "Use /incident help"
            )
        subcommand = match.group(1).lower()
        args = match.group(2) or ""
        handlers = {
            "status": self._handle_status,
            "search": self._handle_search,
            "recent": self._handle_recent,
            "runbook": self._handle_runbook,
            "ask": self._handle_ask,
            "summarize": self._handle_summarize,
            "suggest": self._handle_suggest,
            "warroom": self._handle_warroom,
            "help": self._handle_help,
        }
        handler = handlers.get(subcommand)
        if not handler:
            return BlockKitBuilder.error_response(
                f"Unknown: {subcommand}", "Use /incident help"
            )
        try:
            response = await handler(ctx, args)
            if ctx.public:
                response = BlockKitBuilder.make_public(response)
            return response
        except Exception as e:
            return BlockKitBuilder.error_response("Error", str(e))

    async def _handle_status(self, ctx, args):
        incidents = await incident_store.get_all_incidents()
        stats = await incident_store.get_stats()
        incident_dicts = [
            {
                "incident_id": inc.incident_id,
                "title": inc.title,
                "service_name": inc.service_name,
                "severity": inc.severity.value,
                "status": inc.status,
                "triggered_at": inc.triggered_at,
            }
            for inc in incidents
        ]
        return BlockKitBuilder.status_response(incident_dicts, stats)

    async def _handle_search(self, ctx, args):
        query = args.strip()
        if not query:
            return BlockKitBuilder.error_response(
                "Search query required", "Usage: /incident search <query>"
            )
        incidents = await incident_store.get_all_incidents()
        results = [
            {
                "incident_id": inc.incident_id,
                "title": inc.title,
                "service_name": inc.service_name,
                "severity": inc.severity.value,
            }
            for inc in incidents
            if query.lower() in inc.title.lower()
            or query.lower() in inc.service_name.lower()
        ]
        return BlockKitBuilder.search_response(query, results, len(results))

    async def _handle_recent(self, ctx, args):
        count = 5
        if args.strip():
            try:
                count = max(1, min(int(args.strip()), 20))
            except ValueError:
                return BlockKitBuilder.error_response(
                    "Invalid count", "Use a number 1-20"
                )
        incidents = await incident_store.get_all_incidents()
        incident_dicts = [
            {
                "incident_id": inc.incident_id,
                "title": inc.title,
                "service_name": inc.service_name,
                "severity": inc.severity.value,
                "status": inc.status,
                "triggered_at": inc.triggered_at,
            }
            for inc in incidents[:count]
        ]
        return BlockKitBuilder.recent_response(incident_dicts, count)

    async def _handle_runbook(self, ctx, args):
        service = args.strip()
        if not service:
            return BlockKitBuilder.error_response(
                "Service name required", "Usage: /incident runbook <service>"
            )
        try:
            matches = self.runbook_linker.find_relevant_runbooks(
                query=service, service_name=service, top_k=5, min_score=0.05
            )
            runbook_dicts = [
                {
                    "title": rb.title,
                    "url": rb.url,
                    "source": rb.source,
                    "relevance_score": rb.relevance_score,
                    "matched_terms": rb.matched_terms,
                }
                for rb in matches
            ]
        except Exception:
            runbook_dicts = []
        return BlockKitBuilder.runbook_response(service, runbook_dicts)

    async def _handle_ask(self, ctx, args):
        """Handle /incident ask <incident_id> <question>."""
        parts = args.strip().split(maxsplit=1)
        if len(parts) < 2:
            return BlockKitBuilder.error_response(
                "Usage: /incident ask <incident_id> <question>",
                "Example: /incident ask INC-123 What changed recently?",
            )

        incident_id = parts[0]
        question = parts[1]

        copilot = get_slack_copilot()

        # Check if session exists
        session = copilot.get_session(incident_id)
        if not session:
            # Try to find the incident and start a session
            incidents = await incident_store.get_all_incidents()
            incident = next(
                (i for i in incidents if i.incident_id == incident_id), None
            )
            if incident:
                await copilot.get_or_create_session(
                    incident_id=incident_id,
                    service_name=incident.service_name,
                    context_card=None,
                )

        try:
            response = await copilot.chat(
                incident_id=incident_id,
                user_message=question,
            )
            return BlockKitBuilder.copilot_response(incident_id, question, response)
        except Exception as e:
            logger.error("copilot_ask_error", error=str(e))
            return BlockKitBuilder.error_response("Copilot error", str(e))

    async def _handle_summarize(self, ctx, args):
        """Handle /incident summarize <incident_id>."""
        incident_id = args.strip()
        if not incident_id:
            return BlockKitBuilder.error_response(
                "Incident ID required",
                "Usage: /incident summarize <incident_id>",
            )

        copilot = get_slack_copilot()
        session = copilot.get_session(incident_id)
        if not session:
            return BlockKitBuilder.error_response(
                f"No active session for {incident_id}",
                "Start a session with /incident ask first",
            )

        try:
            summary = await copilot.generate_summary(incident_id)
            if summary:
                return BlockKitBuilder.summary_response(incident_id, summary)
            else:
                return BlockKitBuilder.error_response(
                    "Failed to generate summary",
                    "Try adding more context with /incident ask",
                )
        except Exception as e:
            logger.error("copilot_summarize_error", error=str(e))
            return BlockKitBuilder.error_response("Summary error", str(e))

    async def _handle_suggest(self, ctx, args):
        """Handle /incident suggest <incident_id>."""
        incident_id = args.strip()
        if not incident_id:
            return BlockKitBuilder.error_response(
                "Incident ID required",
                "Usage: /incident suggest <incident_id>",
            )

        copilot = get_slack_copilot()
        session = copilot.get_session(incident_id)
        if not session:
            return BlockKitBuilder.error_response(
                f"No active session for {incident_id}",
                "Start a session with /incident ask first",
            )

        try:
            suggestions = await copilot.suggest_next_steps(incident_id)
            return BlockKitBuilder.suggestions_response(incident_id, suggestions)
        except Exception as e:
            logger.error("copilot_suggest_error", error=str(e))
            return BlockKitBuilder.error_response("Suggestions error", str(e))

    async def _handle_warroom(self, ctx, args=""):
        """Handle /incident warroom <incident_id>."""
        incident_id = args.strip()
        if not incident_id:
            return BlockKitBuilder.error_response(
                "Incident ID required",
                "Usage: /incident warroom <incident_id>",
            )

        # Look up the incident for service name
        incidents = await incident_store.get_all_incidents()
        incident = next((i for i in incidents if i.incident_id == incident_id), None)
        service = incident.service_name if incident else "unknown"

        from ..integrations.slack_lifecycle import create_warroom_from_notification

        try:
            result = await create_warroom_from_notification(
                tenant_id=None,
                incident_id=incident_id,
                service=service,
                original_channel_id=ctx.channel_id,
                original_ts=None,
                context_blocks=None,
            )
            if result:
                return BlockKitBuilder.warroom_response(
                    incident_id, result["channel_id"], result["channel_name"]
                )
            else:
                return BlockKitBuilder.error_response(
                    "War room creation failed",
                    "Check Slack bot permissions and try again.",
                )
        except Exception as e:
            logger.error("warroom_command_error", error=str(e))
            return BlockKitBuilder.error_response("War room error", str(e))

    async def _handle_help(self, ctx, args=""):
        return BlockKitBuilder.help_response()


command_handler = CommandHandler()
