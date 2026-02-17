"""Backward-compatible AI copilot imports.

Historically, callers imported copilot chat/session helpers from `src.ai.copilot`.

After the AI-service boundary refactor, the public API is exposed via `src.ai` and
implemented in `src.ai.adapter`.

This module remains as a thin re-export layer to avoid breaking imports.
"""

from .adapter import AICopilot, ChatMessage, IncidentSession, MessageRole

__all__ = ["AICopilot", "ChatMessage", "IncidentSession", "MessageRole"]
