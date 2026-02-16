"""AI layer — routes through AI service client with local proprietary fallback."""

from .adapter import (
    AICopilot,
    ChatMessage,
    CompressedLogs,
    IncidentSession,
    LogCompressor,
    LogSummarizer,
    MessageRole,
    VerdictEngine,
)
from .client import AIServiceClient, ai_client

__all__ = [
    "AICopilot",
    "AIServiceClient",
    "ChatMessage",
    "CompressedLogs",
    "IncidentSession",
    "LogCompressor",
    "LogSummarizer",
    "MessageRole",
    "VerdictEngine",
    "ai_client",
]
