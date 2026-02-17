"""Backward-compatible log compressor imports.

Historically, callers imported log compression utilities from `src.ai.log_compressor`.

After the AI-service boundary refactor, the public API is exposed via `src.ai` and
implemented in `src.ai.adapter`.

This module remains as a thin re-export layer to avoid breaking imports.
"""

from .adapter import CompressedLogs, LogCompressor

__all__ = ["CompressedLogs", "LogCompressor"]
