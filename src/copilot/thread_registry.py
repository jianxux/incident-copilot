"""In-memory Slack thread to incident registry."""

import asyncio

import structlog

logger = structlog.get_logger()


class ThreadRegistry:
    """Track Slack thread mappings to incident IDs in memory."""

    def __init__(self) -> None:
        self._threads: dict[tuple[str, str, str], str] = {}
        self._lock = asyncio.Lock()

    async def register_thread(
        self,
        team_id: str,
        channel_id: str,
        thread_ts: str,
        incident_id: str,
    ) -> None:
        """Register a Slack thread to incident mapping."""
        key = (team_id or "*", channel_id, thread_ts)
        async with self._lock:
            self._threads[key] = incident_id
        logger.info(
            "copilot_thread_registered",
            team_id=key[0],
            channel_id=channel_id,
            thread_ts=thread_ts,
            incident_id=incident_id,
        )

    async def get_incident_id(
        self, team_id: str, channel_id: str, thread_ts: str
    ) -> str | None:
        """Get incident ID for a Slack thread if a mapping exists."""
        async with self._lock:
            exact_key = (team_id, channel_id, thread_ts)
            wildcard_key = ("*", channel_id, thread_ts)
            return self._threads.get(exact_key) or self._threads.get(wildcard_key)


thread_registry = ThreadRegistry()
