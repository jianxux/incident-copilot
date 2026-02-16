"""AI layer — routes through AI service client or returns stub responses."""

from .adapter import (
    AICopilot,
    ChatMessage,
    CompressedLogs,
    ConfidenceLevel,
    IncidentSession,
    LogCompressor,
    LogSummarizer,
    MessageRole,
    Verdict,
    VerdictEngine,
)
from .client import AIServiceClient, ai_client

__all__ = [
    "AICopilot",
    "AIServiceClient",
    "ChatMessage",
    "CompressedLogs",
    "ConfidenceLevel",
    "IncidentSession",
    "LogCompressor",
    "LogSummarizer",
    "MessageRole",
    "Verdict",
    "VerdictEngine",
    "ai_client",
]
