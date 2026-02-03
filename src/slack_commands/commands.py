"""Command handlers for Slack slash commands."""

import re
from dataclasses import dataclass
from typing import Any

import structlog

from ..runbooks import RunbookLinker
from ..web.store import incident_store
from .responses import BlockKitBuilder

logger = structlog.get_logger()


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
        except:
            runbook_dicts = []
        return BlockKitBuilder.runbook_response(service, runbook_dicts)

    async def _handle_help(self, ctx, args=""):
        return BlockKitBuilder.help_response()


command_handler = CommandHandler()
