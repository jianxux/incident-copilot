"""Backward-compatible verdict engine imports.

Historically, callers imported verdict types from `src.ai.verdict`.

After the AI-service boundary refactor, the public API is exposed via `src.ai` and
implemented in `src.ai.adapter`.

This module remains as a thin re-export layer to avoid breaking imports.
"""

from .adapter import ConfidenceLevel, Verdict, VerdictEngine

__all__ = ["ConfidenceLevel", "Verdict", "VerdictEngine"]
