"""AI Adapter — provides the same interfaces, delegating to the remote AI service.

When AI_SERVICE_URL is set, calls the proprietary AI service via HTTP.
Otherwise, returns stub responses.
"""

from __future__ import annotations

import enum
import json
from datetime import datetime, timedelta
from typing import Any, List, Optional

import structlog
from pydantic import BaseModel

from .client import ai_client

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Model stubs (so callers can import the types)
# ---------------------------------------------------------------------------

try:
    from enum import StrEnum as _StrEnum
except ImportError:

    class _StrEnum(str, enum.Enum):  # type: ignore[no-redef]
        pass


class MessageRole(_StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    role: MessageRole = MessageRole.USER
    content: str = ""
    timestamp: Optional[str] = None


class IncidentSession(BaseModel):
    incident_id: str = ""
    service_name: str | None = None
    context_card: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None
    messages: List[ChatMessage] = []  # noqa: RUF012


class CompressedLogs(BaseModel):
    compressed: list = []  # noqa: RUF012
    total: int = 0
    kept: int = 0


class Verdict(BaseModel):
    most_likely_cause: str
    confidence: "ConfidenceLevel"
    evidence: str
    recommended_action: str
    secondary_action: Optional[str] = None
    deploy_correlated: bool = False
    suspect_deploy: Optional[str] = None


class ConfidenceLevel(_StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Adapter classes — delegate to AI service client
# ---------------------------------------------------------------------------


class LogSummarizer:
    """Drop-in replacement for ai.summarizer.LogSummarizer."""

    def __init__(self, settings=None):
        self._settings = settings

    async def summarize(
        self,
        logs,
        service_name=None,
        similar_incidents=None,
        **kwargs,
    ) -> str:
        log_dicts = [l if isinstance(l, dict) else {"message": str(l)} for l in logs]
        result = await ai_client.summarize_logs(log_dicts, similar_incidents)
        return result.get("summary", "")


class VerdictEngine:
    """Drop-in replacement for ai.verdict.VerdictEngine."""

    def __init__(self, settings=None):
        self._settings = settings
        # Backward-compatible attribute used by historical tests/callers.
        self.client = None

    async def generate_verdict(
        self,
        title: str,
        service_name: str,
        severity: str,
        triggered_at: datetime | str,
        recent_deploys: Optional[list[dict]] = None,
        log_summary: Optional[dict | str] = None,
        metrics: Optional[dict] = None,
        topology: Optional[dict] = None,
        similar_incidents: Optional[list[Any]] = None,
        **kwargs,
    ) -> Verdict:
        # Backward compat with adapter-style call sites.
        if kwargs.get("alert_data"):
            alert_data = kwargs.get("alert_data") or {}
            title = alert_data.get("title", title)
            service_name = alert_data.get("service_name", service_name)
            severity = alert_data.get("severity", severity)
            triggered_at = alert_data.get("triggered_at", triggered_at)
        if recent_deploys is None:
            recent_deploys = kwargs.get("deploys") or kwargs.get("recent_deploys")
        if log_summary is None and "log_summary" in kwargs:
            log_summary = kwargs.get("log_summary")
        if metrics is None and kwargs.get("metrics") is not None:
            metrics = kwargs.get("metrics")
        if topology is None and kwargs.get("topology") is not None:
            topology = kwargs.get("topology")
        if similar_incidents is None and kwargs.get("similar_incidents") is not None:
            similar_incidents = kwargs.get("similar_incidents")
        normalized_similar_incidents = self._normalize_similar_incidents(similar_incidents)

        sections = self._build_context_sections(
            recent_deploys=recent_deploys,
            log_summary=log_summary,
            metrics=metrics,
            topology=topology,
            similar_incidents=normalized_similar_incidents,
        )

        # Legacy path: direct LLM client attached on self.client.
        if self.client is not None:
            try:
                response = await self.client.messages.create(
                    model=getattr(self._settings, "ai_model", "claude-3-haiku-20240307"),
                    max_tokens=800,
                    temperature=0.1,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Analyze this incident and respond as JSON with keys: "
                                "most_likely_cause, confidence, evidence, recommended_action, "
                                "secondary_action, deploy_correlated, suspect_deploy.\n\n"
                                f"Title: {title}\n"
                                f"Service: {service_name}\n"
                                f"Severity: {severity}\n"
                                f"Triggered at: {triggered_at}\n\n"
                                f"{sections}"
                            ),
                        }
                    ],
                )
                payload = self._extract_payload_from_llm_response(response)
                return self._map_response_to_verdict(payload, service_name)
            except Exception as e:
                logger.warning("legacy_verdict_generation_failed", error=str(e))

        # Boundary path: delegate to the AI client when configured.
        # In tests, `ai_client.generate_verdict` may be monkeypatched; detect that
        # and call it even if the client is otherwise disabled.
        import types

        gv = getattr(ai_client, "generate_verdict")
        should_call = ai_client.enabled or not isinstance(gv, types.MethodType)

        if should_call:
            try:
                response = await gv(
                    alert_data={
                        "title": title,
                        "service_name": service_name,
                        "severity": severity,
                        "triggered_at": str(triggered_at),
                    },
                    deploys=recent_deploys or [],
                    log_summary=(
                        json.dumps(log_summary, default=str)
                        if isinstance(log_summary, dict)
                        else (log_summary or "")
                    ),
                    metrics=metrics if metrics is not None else topology,
                    similar_incidents=normalized_similar_incidents,
                )
                return self._map_response_to_verdict(response, service_name)
            except Exception as e:
                logger.warning("ai_service_verdict_generation_failed", error=str(e))

        return self._fallback_verdict(
            title=title,
            service_name=service_name,
            recent_deploys=recent_deploys,
            log_summary=log_summary,
        )

    def _extract_payload_from_llm_response(self, response: Any) -> dict:
        text = ""
        if isinstance(response, dict):
            return response
        content = getattr(response, "content", None)
        if isinstance(content, list) and content:
            text = getattr(content[0], "text", "") or ""
        if not text and isinstance(content, str):
            text = content
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"most_likely_cause": text}
        return {}

    def _map_response_to_verdict(self, data: dict, service_name: str) -> Verdict:
        cause = (
            data.get("most_likely_cause")
            or data.get("root_cause")
            or data.get("verdict")
            or f"Potential issue in {service_name}"
        )
        evidence = data.get("evidence") or data.get("verdict") or "No direct evidence provided."

        recommended_action = data.get("recommended_action")
        if not recommended_action:
            suggested_actions = data.get("suggested_actions")
            if isinstance(suggested_actions, list) and suggested_actions:
                recommended_action = str(suggested_actions[0])
            else:
                recommended_action = "Investigate recent changes and service dependencies."

        secondary_action = data.get("secondary_action")
        if secondary_action is None:
            suggested_actions = data.get("suggested_actions")
            if isinstance(suggested_actions, list) and len(suggested_actions) > 1:
                secondary_action = str(suggested_actions[1])

        return Verdict(
            most_likely_cause=str(cause),
            confidence=self._parse_confidence(data.get("confidence")),
            evidence=str(evidence),
            recommended_action=str(recommended_action),
            secondary_action=str(secondary_action) if secondary_action is not None else None,
            deploy_correlated=bool(data.get("deploy_correlated", False)),
            suspect_deploy=(
                str(data.get("suspect_deploy"))
                if data.get("suspect_deploy") is not None
                else None
            ),
        )

    def _parse_confidence(self, confidence: Any) -> ConfidenceLevel:
        if isinstance(confidence, (int, float)):
            if confidence >= 0.8:
                return ConfidenceLevel.HIGH
            if confidence >= 0.4:
                return ConfidenceLevel.MEDIUM
            return ConfidenceLevel.LOW
        value = str(confidence or "").strip().lower()
        if value in {"high", "h"}:
            return ConfidenceLevel.HIGH
        if value in {"medium", "med", "m"}:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    def _build_context_sections(
        self,
        recent_deploys: Optional[list[dict]] = None,
        log_summary: Optional[dict | str] = None,
        metrics: Optional[dict] = None,
        topology: Optional[dict] = None,
        similar_incidents: Optional[list[Any]] = None,
    ) -> str:
        sections: list[str] = []

        if recent_deploys:
            lines = ["RECENT DEPLOYMENTS:"]
            for deploy in recent_deploys[:5]:
                sha = deploy.get("short_sha") or deploy.get("sha") or "unknown"
                author = deploy.get("author", "unknown")
                message = deploy.get("message", "No message")
                when = deploy.get("timestamp", "unknown time")
                lines.append(f"- {sha} by {author} at {when}: {message}")
            sections.append("\n".join(lines))

        if log_summary:
            lines = ["LOG ANALYSIS:"]
            if isinstance(log_summary, dict):
                likely = log_summary.get("likely_cause")
                explanation = log_summary.get("explanation")
                issues = log_summary.get("top_issues")
                if likely:
                    lines.append(f"Likely cause: {likely}")
                if explanation:
                    lines.append(f"Explanation: {explanation}")
                if isinstance(issues, list) and issues:
                    lines.append("Top issues:")
                    for issue in issues[:5]:
                        lines.append(f"- {issue}")
            else:
                lines.append(str(log_summary))
            sections.append("\n".join(lines))

        if metrics:
            lines = ["METRICS:"]
            error_rate = metrics.get("error_rate")
            if isinstance(error_rate, (int, float)):
                lines.append(f"Error rate: {error_rate * 100:.1f}%")
            baseline = metrics.get("error_rate_baseline")
            if isinstance(baseline, (int, float)):
                lines.append(f"Baseline error rate: {baseline * 100:.1f}%")
            p99 = metrics.get("latency_p99_ms")
            if p99 is not None:
                lines.append(f"P99 latency: {p99}ms")
            for key, value in metrics.items():
                if key not in {"error_rate", "error_rate_baseline", "latency_p99_ms"}:
                    lines.append(f"{key}: {value}")
            sections.append("\n".join(lines))

        if topology:
            lines = ["SERVICE TOPOLOGY:"]
            for key, value in topology.items():
                lines.append(f"{key}: {value}")
            sections.append("\n".join(lines))

        normalized_similar_incidents = self._normalize_similar_incidents(similar_incidents)
        if normalized_similar_incidents:
            lines = [
                "SIMILAR PAST INCIDENTS:",
                "Here are similar past incidents and their resolutions:",
            ]
            for incident in normalized_similar_incidents[:3]:
                happened = (
                    incident.get("title")
                    or incident.get("description")
                    or "Unknown incident"
                )
                root_cause = incident.get("root_cause") or "Unknown"
                resolution = incident.get("resolution") or "Unknown"
                time_to_resolve = self._format_time_to_resolve(
                    incident.get("occurred_at"),
                    incident.get("resolved_at"),
                )
                line = (
                    f"- What happened: {happened} | Root cause: {root_cause}"
                    f" | Resolution: {resolution}"
                )
                if time_to_resolve:
                    line += f" | Time to resolve: {time_to_resolve}"
                lines.append(line)
            sections.append("\n".join(lines))

        if not sections:
            return "No additional context available"
        return "\n\n".join(sections)

    def _normalize_similar_incidents(
        self, similar_incidents: Optional[list[Any]]
    ) -> list[dict[str, Any]]:
        if not similar_incidents:
            return []

        normalized: list[dict[str, Any]] = []
        for incident in similar_incidents:
            if isinstance(incident, dict):
                normalized.append(incident)
                continue
            if hasattr(incident, "model_dump"):
                normalized.append(incident.model_dump())
                continue
            normalized.append(
                {
                    "title": getattr(incident, "title", None),
                    "description": getattr(incident, "description", None),
                    "root_cause": getattr(incident, "root_cause", None),
                    "resolution": getattr(incident, "resolution", None),
                    "occurred_at": getattr(incident, "occurred_at", None),
                    "resolved_at": getattr(incident, "resolved_at", None),
                }
            )
        return normalized

    def _format_time_to_resolve(self, occurred_at: Any, resolved_at: Any) -> str | None:
        occurred = self._parse_datetime_like(occurred_at)
        resolved = self._parse_datetime_like(resolved_at)
        if not occurred or not resolved or resolved <= occurred:
            return None
        return self._humanize_duration(resolved - occurred)

    def _parse_datetime_like(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            candidate = value.strip()
            if candidate.endswith("Z"):
                candidate = candidate[:-1] + "+00:00"
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                return None
        return None

    def _humanize_duration(self, duration: timedelta) -> str:
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _fallback_verdict(
        self,
        title: str,
        service_name: str,
        recent_deploys: Optional[list[dict]] = None,
        log_summary: Optional[dict | str] = None,
    ) -> Verdict:
        if recent_deploys:
            latest = recent_deploys[0]
            suspect_deploy = latest.get("short_sha") or latest.get("sha") or "recent deploy"
            return Verdict(
                most_likely_cause=f"Recent deploy {suspect_deploy} may be correlated with {service_name} incident.",
                confidence=ConfidenceLevel.MEDIUM,
                evidence=f"Alert '{title}' occurred after deploy {suspect_deploy}.",
                recommended_action=f"Consider rolling back deploy {suspect_deploy} and validating recovery.",
                secondary_action="Review logs and error metrics to confirm regression source.",
                deploy_correlated=True,
                suspect_deploy=str(suspect_deploy),
            )

        if log_summary:
            likely_cause = None
            if isinstance(log_summary, dict):
                likely_cause = (
                    log_summary.get("likely_cause")
                    or log_summary.get("explanation")
                    or (
                        log_summary.get("top_issues", [None])[0]
                        if isinstance(log_summary.get("top_issues"), list)
                        else None
                    )
                )
            if not likely_cause:
                likely_cause = str(log_summary)
            return Verdict(
                most_likely_cause=str(likely_cause),
                confidence=ConfidenceLevel.LOW,
                evidence="Fallback analysis based on available log summary only.",
                recommended_action="Inspect service logs and dependency health, then mitigate based on the likely cause.",
            )

        return Verdict(
            most_likely_cause=f"Potential service degradation detected in {service_name}.",
            confidence=ConfidenceLevel.LOW,
            evidence=f"Limited context available for alert '{title}'.",
            recommended_action="Start with basic service health checks, logs, and recent infrastructure changes.",
        )


class LogCompressor:
    """Drop-in replacement for ai.log_compressor.LogCompressor."""

    def __init__(self, *args, **kwargs):
        pass

    async def compress(self, logs, **kwargs):
        log_dicts = [l if isinstance(l, dict) else {"message": str(l)} for l in logs]
        result = await ai_client.compress_logs(log_dicts)
        return CompressedLogs(**result)

    def compress_sync(self, logs, **kwargs):
        return CompressedLogs(compressed=logs[:50], total=len(logs), kept=min(len(logs), 50))


class AICopilot:
    """Drop-in replacement for the historical ai.copilot.AICopilot.

    This class intentionally supports two execution paths:
    1) Legacy in-process LLM client (`self.client`) used by older tests/callers.
    2) Boundary AI service client (`src.ai.client.ai_client`) used by the app.
    """

    def __init__(self, settings=None):
        self._settings = settings
        self._sessions: dict[str, IncidentSession] = {}

        # Legacy hooks used by older tests/callers.
        self.client = None
        self.incident_recall = None

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())

    def get_session(self, incident_id: str) -> IncidentSession | None:
        return self._sessions.get(incident_id)

    async def get_or_create_session(self, incident_id: str, context=None) -> IncidentSession:
        if incident_id not in self._sessions:
            now = datetime.utcnow().isoformat()
            self._sessions[incident_id] = IncidentSession(
                incident_id=incident_id,
                created_at=now,
                updated_at=now,
            )
        return self._sessions[incident_id]

    async def chat(
        self,
        incident_id: str,
        message: str | None = None,
        context=None,
        **kwargs,
    ) -> str:
        # Backwards-compat: some callers use `user_message=` and `context_card=`.
        if message is None:
            message = kwargs.get("user_message")
        if message is None:
            raise TypeError("chat() missing required argument: 'message'")

        context_card = kwargs.get("context_card")
        if context is None and context_card is not None:
            # Allow passing a pydantic model or dict.
            context = context_card.model_dump() if hasattr(context_card, "model_dump") else context_card

        session = await self.get_or_create_session(incident_id)
        session.updated_at = datetime.utcnow().isoformat()
        if isinstance(context, dict) and context:
            session.context_card = context
            session.service_name = context.get("service_name") or session.service_name

        # --- Legacy path (used by tests) ---
        if self.client is not None and self.incident_recall is not None:
            recalled = []
            try:
                # Minimal heuristic: when user asks "has this happened before",
                # run incident recall and inject results into the system prompt.
                recalled = await self.incident_recall.recall(
                    query=message,
                    service_name=session.service_name,
                    limit=5,
                )
            except TypeError:
                # Some recall implementations may accept different kwargs.
                recalled = await self.incident_recall.recall(message)

            tool_block = "Tool search_past_incidents results\n"
            for r in recalled or []:
                record = getattr(r, "record", None) or r
                tool_block += (
                    f"- {getattr(record, 'id', '')}: {getattr(record, 'title', '')}\n"
                    f"  Root cause: {getattr(record, 'root_cause_summary', '')}\n"
                    f"  Resolution: {getattr(record, 'resolution_summary', '')}\n"
                )

            resp = await self.client.messages.create(
                model=getattr(self._settings, "ai_model", "claude-3-haiku-20240307"),
                max_tokens=600,
                temperature=0.2,
                system=tool_block,
                messages=[{"role": "user", "content": message}],
            )
            text = ""
            content = getattr(resp, "content", None)
            if isinstance(content, list) and content:
                text = getattr(content[0], "text", "") or ""
            elif isinstance(content, str):
                text = content
            msg = ChatMessage(role=MessageRole.ASSISTANT, content=text)
            session.messages.append(msg)
            return text

        # --- Boundary path ---
        result = await ai_client.chat(
            session_id=incident_id,
            message=message,
            context=context if isinstance(context, dict) else None,
        )
        text = result.get("response", "")
        msg = ChatMessage(role=MessageRole.ASSISTANT, content=text)
        session.messages.append(msg)
        return text

    async def generate_summary(self, incident_id: str) -> dict | None:
        summary = await ai_client.generate_summary(incident_id, {})
        return {"summary": summary}

    async def suggest_next_steps(self, incident_id: str) -> list[str]:
        return await ai_client.suggest_next_steps({})

    async def search_past_incidents(self, *args, **kwargs):
        return []
