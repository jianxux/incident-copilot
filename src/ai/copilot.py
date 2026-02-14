"""AI Copilot - Interactive incident assistant for on-call engineers."""

import json
from datetime import datetime
from enum import StrEnum
from typing import cast

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam
from pydantic import BaseModel

from ..config import Settings
from ..memory import (
    IncidentMemoryConfig,
    IncidentMemoryStore,
    IncidentRecall,
    RecallQuery,
)
from ..memory.models import IncidentRecallResult
from ..models import ContextCard, PastIncident

logger = structlog.get_logger()


class MessageRole(StrEnum):
    """Chat message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """A single chat message."""

    role: MessageRole
    content: str
    timestamp: datetime = None

    def __init__(self, **data):
        if "timestamp" not in data or data["timestamp"] is None:
            data["timestamp"] = datetime.utcnow()
        super().__init__(**data)


class IncidentSession(BaseModel):
    """Active incident investigation session with conversation history."""

    incident_id: str
    service_name: str
    context_card: ContextCard | None = None
    messages: list[ChatMessage] = []
    created_at: datetime = None
    updated_at: datetime = None

    def __init__(self, **data):
        now = datetime.utcnow()
        if "created_at" not in data or data["created_at"] is None:
            data["created_at"] = now
        if "updated_at" not in data or data["updated_at"] is None:
            data["updated_at"] = now
        super().__init__(**data)


COPILOT_SYSTEM_PROMPT = """You are an expert SRE incident copilot helping an on-call engineer troubleshoot a live incident. You have access to context about the incident including recent deployments, error logs, metrics, and past similar incidents.

Your job is to:
1. Help the engineer understand what's happening
2. Suggest concrete next steps to investigate or resolve
3. Point out patterns or correlations in the data
4. Reference similar past incidents if relevant
5. Be concise and actionable - this is a live incident

Current Incident Context:
{context}

Guidelines:
- Be direct and actionable. Time matters during incidents.
- If you see a likely root cause, say so clearly
- Suggest specific commands, queries, or checks when relevant
- If you need more information, ask specific questions
- Reference the context data when making suggestions
- If something looks like a recent deployment issue, call it out immediately

You are part of the incident response team. Help them resolve this quickly."""


SUMMARY_PROMPT = """Based on the incident context and investigation conversation below, generate a concise incident summary suitable for a postmortem or handoff.

Incident Context:
{context}

Investigation Conversation:
{conversation}

Generate a JSON response with:
{{
  "title": "Brief incident title",
  "summary": "2-3 sentence summary of what happened",
  "timeline": [
    {{"time": "HH:MM", "event": "description"}}
  ],
  "root_cause": "Identified or suspected root cause",
  "resolution": "How it was resolved (or current status)",
  "action_items": ["Follow-up actions to prevent recurrence"],
  "severity_assessment": "P1/P2/P3/P4 with brief justification"
}}

Be factual and concise. Only include what's supported by the context and conversation."""


class AICopilot:
    """Interactive AI copilot for incident investigation."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            AsyncAnthropic(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )
        self.model = settings.ai_model
        # In-memory session store (use Redis in production)
        self._sessions: dict[str, IncidentSession] = {}
        self.memory_config = IncidentMemoryConfig.from_settings(settings)
        self.memory_store: IncidentMemoryStore | None = None
        self.incident_recall: IncidentRecall | None = None
        if self.memory_config.enabled:
            try:
                self.memory_store = IncidentMemoryStore(
                    database_url=self.memory_config.database_url,
                    config=self.memory_config,
                )
                self.incident_recall = IncidentRecall(
                    settings=settings,
                    store=self.memory_store,
                    config=self.memory_config,
                )
            except Exception as e:
                logger.warning("copilot_incident_memory_init_failed", error=str(e))
                self.memory_store = None
                self.incident_recall = None

    def _format_context(self, card: ContextCard | None) -> str:
        """Format context card for the AI prompt."""
        if not card:
            return "No context available yet."

        parts = [
            f"**Incident:** {card.title}",
            f"**Service:** {card.service_name}",
            f"**Severity:** {card.severity.value if card.severity else 'Unknown'}",
            f"**Triggered:** {card.triggered_at.isoformat() if card.triggered_at else 'Unknown'}",
        ]

        if card.owners:
            parts.append(f"**Owners:** {', '.join(card.owners)}")

        if card.github:
            parts.append("\n**Recent Deployments (GitHub):**")
            for deploy in card.github.recent_deploys[:5]:
                parts.append(
                    f"  - {deploy.sha[:7]} by {deploy.author}: {deploy.message[:60]}"
                )

        if card.gitlab:
            parts.append("\n**Recent Deployments (GitLab):**")
            for deploy in card.gitlab.recent_deploys[:5]:
                parts.append(
                    f"  - {deploy.sha[:7]} by {deploy.author}: {deploy.message[:60]}"
                )

        if card.ai_summary:
            parts.append("\n**AI Log Analysis:**")
            parts.append(f"  Explanation: {card.ai_summary.explanation}")
            if card.ai_summary.likely_cause:
                parts.append(f"  Likely Cause: {card.ai_summary.likely_cause}")
            if card.ai_summary.top_issues:
                parts.append("  Top Issues:")
                for issue in card.ai_summary.top_issues[:3]:
                    parts.append(f"    - {issue}")

        if card.datadog and card.datadog.logs:
            parts.append(f"\n**Recent Logs:** {len(card.datadog.logs)} entries")
            for log in card.datadog.logs[:5]:
                parts.append(
                    f"  [{log.timestamp.strftime('%H:%M:%S')}] {log.level}: {log.message[:100]}"
                )

        if card.runbooks:
            parts.append("\n**Relevant Runbooks:**")
            for rb in card.runbooks[:3]:
                parts.append(f"  - [{rb.title}]({rb.url})")

        if card.similar_incidents:
            parts.append("\n**Similar Past Incidents:**")
            for past in card.similar_incidents[:3]:
                score = (
                    f"{past.similarity_score:.0f}%"
                    if past.similarity_score is not None
                    else "n/a"
                )
                line = f"  - {past.title} ({past.occurred_at.date().isoformat()}, match={score})"
                if past.severity:
                    line += f", severity={past.severity}"
                parts.append(line)
                if past.root_cause:
                    parts.append(f"    root_cause: {past.root_cause[:180]}")
                if past.resolution:
                    parts.append(f"    resolution: {past.resolution[:180]}")

        if card.oncall:
            parts.append(f"\n**On-Call:** {', '.join(card.oncall.oncall_names)}")

        if card.errors:
            parts.append(f"\n**Context Fetch Errors:** {', '.join(card.errors)}")

        return "\n".join(parts)

    def _format_conversation(self, messages: list[ChatMessage]) -> str:
        """Format conversation history for summary generation."""
        lines = []
        for msg in messages:
            role = "Engineer" if msg.role == MessageRole.USER else "Copilot"
            time_str = msg.timestamp.strftime("%H:%M") if msg.timestamp else ""
            lines.append(f"[{time_str}] {role}: {msg.content}")
        return "\n".join(lines)

    async def get_or_create_session(
        self,
        incident_id: str,
        service_name: str,
        context_card: ContextCard | None = None,
    ) -> IncidentSession:
        """Get existing session or create new one."""
        if incident_id in self._sessions:
            session = self._sessions[incident_id]
            if context_card:
                session.context_card = context_card
                session.updated_at = datetime.utcnow()
            return session

        session = IncidentSession(
            incident_id=incident_id,
            service_name=service_name,
            context_card=context_card,
        )
        self._sessions[incident_id] = session
        logger.info("copilot_session_created", incident_id=incident_id)
        return session

    async def chat(
        self,
        incident_id: str,
        user_message: str,
        context_card: ContextCard | None = None,
    ) -> str:
        """Send a message and get AI response."""
        if not self.client:
            return "AI copilot not configured. Set ANTHROPIC_API_KEY to enable."

        # Get or create session
        session = await self.get_or_create_session(
            incident_id=incident_id,
            service_name=context_card.service_name if context_card else "unknown",
            context_card=context_card,
        )

        # Add user message
        session.messages.append(
            ChatMessage(role=MessageRole.USER, content=user_message)
        )
        session.updated_at = datetime.utcnow()

        try:
            # Build messages for API
            context_str = self._format_context(session.context_card)
            if self._should_use_past_incidents_tool(user_message):
                tool_results = await self.search_past_incidents(
                    incident_id=incident_id,
                    query=user_message,
                    context_card=session.context_card,
                    limit=3,
                )
                if tool_results:
                    context_str += (
                        "\n\n**Tool search_past_incidents results:**\n"
                        + self._format_past_incidents_for_tool_context(tool_results)
                    )

            system_prompt = COPILOT_SYSTEM_PROMPT.format(context=context_str)

            api_messages: list[MessageParam] = cast(
                list[MessageParam],
                [
                    {"role": msg.role.value, "content": msg.content}
                    for msg in session.messages
                    if msg.role != MessageRole.SYSTEM
                ],
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=api_messages,
            )

            assistant_message = "".join(
                getattr(block, "text", "") for block in response.content
            )

            # Add assistant response to history
            session.messages.append(
                ChatMessage(role=MessageRole.ASSISTANT, content=assistant_message)
            )

            logger.info(
                "copilot_response",
                incident_id=incident_id,
                message_count=len(session.messages),
            )

            return assistant_message

        except Exception as e:
            logger.error("copilot_chat_error", incident_id=incident_id, error=str(e))
            return f"Sorry, I encountered an error: {str(e)}"

    async def search_past_incidents(
        self,
        incident_id: str,
        query: str,
        context_card: ContextCard | None,
        limit: int = 3,
    ) -> list[PastIncident]:
        """Recall past incidents relevant to the current conversation."""
        if not self.incident_recall:
            return []

        services = (
            [context_card.service_name]
            if context_card and context_card.service_name
            else []
        )
        severity = (
            context_card.severity.value
            if context_card and context_card.severity
            else None
        )
        narrative_parts = [query.strip() or f"investigation for {incident_id}"]
        if context_card:
            narrative_parts.append(context_card.title)
            if context_card.ai_summary and context_card.ai_summary.explanation:
                narrative_parts.append(context_card.ai_summary.explanation)

        try:
            recall_query = RecallQuery(
                narrative="\n".join(narrative_parts),
                incident_id=incident_id,
                services=services,
                severity=severity,
                lookback_days=180,
                limit=limit,
            )
            matches = await self.incident_recall.recall(recall_query)
            return self._map_recall_results_to_past_incidents(matches)
        except Exception as e:
            logger.warning(
                "copilot_search_past_incidents_failed",
                incident_id=incident_id,
                error=str(e),
            )
            return []

    def _should_use_past_incidents_tool(self, message: str) -> bool:
        """Decide when to call search_past_incidents during chat."""
        normalized = message.lower()
        triggers = (
            "past incident",
            "similar incident",
            "happened before",
            "has this happened before",
            "previous incident",
            "historical incident",
        )
        return any(trigger in normalized for trigger in triggers)

    def _format_past_incidents_for_tool_context(
        self, incidents: list[PastIncident]
    ) -> str:
        """Format tool output for the LLM context."""
        lines: list[str] = []
        for incident in incidents[:3]:
            score = (
                f"{incident.similarity_score:.0f}%"
                if incident.similarity_score is not None
                else "n/a"
            )
            line = f"- {incident.title} ({incident.occurred_at.date().isoformat()}, match={score})"
            if incident.severity:
                line += f", severity={incident.severity}"
            lines.append(line)
            if incident.root_cause:
                lines.append(f"  root_cause: {incident.root_cause[:180]}")
            if incident.resolution:
                lines.append(f"  resolution: {incident.resolution[:180]}")
        return "\n".join(lines)

    def _map_recall_results_to_past_incidents(
        self, recalled: list[IncidentRecallResult]
    ) -> list[PastIncident]:
        """Map Incident Memory recall results to copilot past incident shape."""
        mapped: list[PastIncident] = []
        for item in recalled:
            record = item.record
            service = (
                record.services_affected[0]
                if record.services_affected
                else "unknown-service"
            )
            resolution = record.resolution_summary
            if not resolution and record.resolution_steps:
                resolution = "; ".join(record.resolution_steps[:3])
            mapped.append(
                PastIncident(
                    incident_id=record.id,
                    title=record.title,
                    service=service,
                    severity=record.severity,
                    root_cause=record.root_cause_summary,
                    resolution=resolution,
                    occurred_at=record.created_at,
                    resolved_at=record.resolved_at,
                    similarity_score=self._normalize_similarity_percent(item.score),
                )
            )
        return mapped

    @staticmethod
    def _normalize_similarity_percent(raw_score: float | None) -> float | None:
        if raw_score is None:
            return None
        if raw_score <= 1.0:
            return round(max(raw_score, 0.0) * 100, 1)
        return round(min(raw_score, 100.0), 1)

    async def generate_summary(self, incident_id: str) -> dict | None:
        """Generate incident summary from context and conversation."""
        if not self.client:
            logger.warning("copilot_not_configured")
            return None

        session = self._sessions.get(incident_id)
        if not session:
            logger.warning("copilot_session_not_found", incident_id=incident_id)
            return None

        try:
            context_str = self._format_context(session.context_card)
            conversation_str = self._format_conversation(session.messages)

            prompt = SUMMARY_PROMPT.format(
                context=context_str, conversation=conversation_str
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            content = "".join(getattr(block, "text", "") for block in response.content)

            # Parse JSON response
            # Handle markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            summary = json.loads(content.strip())

            logger.info("copilot_summary_generated", incident_id=incident_id)
            return summary

        except json.JSONDecodeError as e:
            logger.error(
                "copilot_summary_json_error", incident_id=incident_id, error=str(e)
            )
            return None
        except Exception as e:
            logger.error("copilot_summary_error", incident_id=incident_id, error=str(e))
            return None

    async def suggest_next_steps(self, incident_id: str) -> list[str]:
        """Get proactive suggestions based on current context."""
        if not self.client:
            return []

        session = self._sessions.get(incident_id)
        if not session or not session.context_card:
            return []

        try:
            context_str = self._format_context(session.context_card)

            prompt = f"""Based on this incident context, suggest 3-5 specific next steps the on-call engineer should take. Be concrete and actionable.

Context:
{context_str}

Respond with a JSON array of strings, each being a specific action:
["Check X", "Run Y command", "Look at Z dashboard"]"""

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            content = "".join(getattr(block, "text", "") for block in response.content)
            if "```" in content:
                content = content.split("```")[1].split("```")[0]
                if content.startswith("json"):
                    content = content[4:]

            suggestions = json.loads(content.strip())
            return suggestions if isinstance(suggestions, list) else []

        except Exception as e:
            logger.error(
                "copilot_suggestions_error", incident_id=incident_id, error=str(e)
            )
            return []

    def get_session(self, incident_id: str) -> IncidentSession | None:
        """Get an existing session."""
        return self._sessions.get(incident_id)

    def list_sessions(self) -> list[str]:
        """List all active session incident IDs."""
        return list(self._sessions.keys())

    def clear_session(self, incident_id: str) -> bool:
        """Clear a session."""
        if incident_id in self._sessions:
            del self._sessions[incident_id]
            logger.info("copilot_session_cleared", incident_id=incident_id)
            return True
        return False
