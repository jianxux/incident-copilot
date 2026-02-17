"""Unit tests for the (public) log compressor adapter.

The detailed, proprietary log parsing/ranking implementation was moved behind the
AI-service boundary.

Public repo contract:
- `LogCompressor.compress_sync()` returns a `CompressedLogs` object
- `LogCompressor.compress()` returns a `CompressedLogs` object (stubbed when
  AI_SERVICE_URL is not configured)
"""

import pytest

from src.ai import CompressedLogs, LogCompressor


class TestLogCompressorAdapter:
    def test_compress_sync_truncates(self):
        compressor = LogCompressor()
        logs = [{"message": f"line {i}"} for i in range(123)]

        result = compressor.compress_sync(logs)

        assert isinstance(result, CompressedLogs)
        assert result.total == 123
        assert result.kept == 50
        assert len(result.compressed) == 50

    @pytest.mark.anyio
    async def test_compress_async_stub(self):
        compressor = LogCompressor()
        logs = [{"message": f"line {i}", "level": "error"} for i in range(3)]

        result = await compressor.compress(logs)

        assert isinstance(result, CompressedLogs)
        assert result.total == 3
        assert result.kept == 3
        assert len(result.compressed) == 3
