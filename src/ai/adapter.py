"""AI Adapter — provides the same interfaces as the proprietary modules.

Resolution order:
1. If AI_SERVICE_URL is set → call remote service via client.py
2. Else try local _proprietary/ imports (for self-hosted / dev)
3. Else use stub responses
"""

from __future__ import annotations

import structlog

from .client import ai_client

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Try importing proprietary implementations as local fallback
# ---------------------------------------------------------------------------
_has_proprietary = False
try:
    from ._proprietary.copilot import AICopilot as _ProprietaryAICopilot
    from ._proprietary.copilot import ChatMessage, IncidentSession, MessageRole
    from ._proprietary.log_compressor import CompressedLogs, LogCompressor as _ProprietaryLogCompressor
    from ._proprietary.summarizer import LogSummarizer as _ProprietaryLogSummarizer
    from ._proprietary.verdict import ConfidenceLevel, Verdict, VerdictEngine as _ProprietaryVerdictEngine

    _has_proprietary = True
    logger.info("ai_adapter_mode", mode="proprietary_local")
except ImportError:
    _has_proprietary = False
    logger.info("ai_adapter_mode", mode="service_or_stub")

    # Provide minimal model stubs so callers can still import the types
    import enum

    from pydantic import BaseModel

    try:
        from enum import StrEnum as _StrEnum
    except ImportError:
        class _StrEnum(str, enum.Enum):  # type: ignore[no-redef]
            pass

    class MessageRole(_StrEnum):  # type: ignore[no-redef]
        USER = "user"
        ASSISTANT = "assistant"
        SYSTEM = "system"

    from typing import Optional, List

    class ChatMessage(BaseModel):  # type: ignore[no-redef]
        role: MessageRole = MessageRole.USER
        content: str = ""
        timestamp: Optional[str] = None

    class IncidentSession(BaseModel):  # type: ignore[no-redef]
        incident_id: str = ""
        messages: List[ChatMessage] = []  # noqa: RUF012

    class CompressedLogs(BaseModel):  # type: ignore[no-redef]
        compressed: list = []  # noqa: RUF012
        total: int = 0
        kept: int = 0

    class Verdict(BaseModel):  # type: ignore[no-redef]
        verdict: str = ""
        confidence: float = 0
        suggested_actions: List[str] = []  # noqa: RUF012
        root_cause: str = ""

    class ConfidenceLevel(_StrEnum):  # type: ignore[no-redef]
        HIGH = "high"
        MEDIUM = "medium"
        LOW = "low"


# ---------------------------------------------------------------------------
# Adapter classes — same interfaces, delegate to service or proprietary
# ---------------------------------------------------------------------------


class LogSummarizer:
    """Drop-in replacement for ai.summarizer.LogSummarizer."""

    def __init__(self, settings=None):
        self._settings = settings
        if _has_proprietary and not ai_client.enabled:
            self._impl = _ProprietaryLogSummarizer(settings)
        else:
            self._impl = None

    async def summarize(self, logs: list[dict], similar_incidents: list[dict] | None = None, **kwargs) -> str:
        if self._impl:
            return await self._impl.summarize(logs, similar_incidents=similar_incidents, **kwargs)
        result = await ai_client.summarize_logs(logs, similar_incidents)
        return result.get("summary", "")


class VerdictEngine:
    """Drop-in replacement for ai.verdict.VerdictEngine."""

    def __init__(self, settings=None):
        self._settings = settings
        if _has_proprietary and not ai_client.enabled:
            self._impl = _ProprietaryVerdictEngine(settings)
        else:
            self._impl = None

    async def generate_verdict(self, alert_data=None, deploys=None, log_summary="", metrics=None, similar_incidents=None, **kwargs):
        if self._impl:
            return await self._impl.generate_verdict(
                alert_data=alert_data,
                deploys=deploys,
                log_summary=log_summary,
                metrics=metrics,
                similar_incidents=similar_incidents,
                **kwargs,
            )
        return await ai_client.generate_verdict(
            alert_data=alert_data or {},
            deploys=deploys or [],
            log_summary=log_summary,
            metrics=metrics,
            similar_incidents=similar_incidents,
        )


class LogCompressor:
    """Drop-in replacement for ai.log_compressor.LogCompressor."""

    def __init__(self, *args, **kwargs):
        if _has_proprietary and not ai_client.enabled:
            self._impl = _ProprietaryLogCompressor(*args, **kwargs)
        else:
            self._impl = None

    async def compress(self, logs, **kwargs):
        if self._impl:
            return await self._impl.compress(logs, **kwargs) if hasattr(self._impl.compress, '__call__') else self._impl.compress(logs, **kwargs)
        result = await ai_client.compress_logs(
            [l if isinstance(l, dict) else {"message": str(l)} for l in logs]
        )
        return CompressedLogs(**result)

    def compress_sync(self, logs, **kwargs):
        """Synchronous compression (used by log_compressor pipeline)."""
        if self._impl and hasattr(self._impl, "compress_sync"):
            return self._impl.compress_sync(logs, **kwargs)
        if self._impl and hasattr(self._impl, "compress"):
            return self._impl.compress(logs, **kwargs)
        return CompressedLogs(compressed=logs[:50], total=len(logs), kept=min(len(logs), 50))


class AICopilot:
    """Drop-in replacement for ai.copilot.AICopilot."""

    def __init__(self, settings=None):
        self._settings = settings
        self._sessions: dict = {}
        if _has_proprietary and not ai_client.enabled:
            self._impl = _ProprietaryAICopilot(settings)
        else:
            self._impl = None

    async def get_or_create_session(self, incident_id: str, context=None):
        if self._impl:
            return await self._impl.get_or_create_session(incident_id, context)
        if incident_id not in self._sessions:
            self._sessions[incident_id] = IncidentSession(incident_id=incident_id)
        return self._sessions[incident_id]

    async def chat(self, incident_id: str, message: str, context=None, **kwargs):
        if self._impl:
            return await self._impl.chat(incident_id, message, context=context, **kwargs)
        result = await ai_client.chat(
            session_id=incident_id,
            message=message,
            context=context if isinstance(context, dict) else None,
        )
        msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=result.get("response", ""),
        )
        session = await self.get_or_create_session(incident_id)
        session.messages.append(msg)
        return msg

    async def generate_summary(self, incident_id: str) -> dict | None:
        if self._impl:
            return await self._impl.generate_summary(incident_id)
        summary = await ai_client.generate_summary(incident_id, {})
        return {"summary": summary}

    async def suggest_next_steps(self, incident_id: str) -> list[str]:
        if self._impl:
            return await self._impl.suggest_next_steps(incident_id)
        return await ai_client.suggest_next_steps({})

    async def search_past_incidents(self, *args, **kwargs):
        if self._impl:
            return await self._impl.search_past_incidents(*args, **kwargs)
        return []
