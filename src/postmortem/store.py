"""Storage for postmortems."""

from datetime import datetime

import structlog

from .models import Postmortem, PostmortemStatus, PostmortemUpdateRequest

logger = structlog.get_logger()


class PostmortemStore:
    """In-memory store for postmortems."""

    def __init__(self):
        self._postmortems: dict[str, Postmortem] = {}
        self._by_incident: dict[str, str] = {}

    async def save(self, postmortem: Postmortem) -> Postmortem:
        """Save a postmortem."""
        postmortem.updated_at = datetime.utcnow()
        self._postmortems[postmortem.id] = postmortem
        self._by_incident[postmortem.incident_id] = postmortem.id
        logger.info(
            "postmortem_saved",
            postmortem_id=postmortem.id,
            incident_id=postmortem.incident_id,
        )
        return postmortem

    async def get(self, postmortem_id: str) -> Postmortem | None:
        """Get a postmortem by ID."""
        return self._postmortems.get(postmortem_id)

    async def get_by_incident(self, incident_id: str) -> Postmortem | None:
        """Get a postmortem by incident ID."""
        postmortem_id = self._by_incident.get(incident_id)
        if postmortem_id:
            return self._postmortems.get(postmortem_id)
        return None

    async def update(self, incident_id: str, updates: PostmortemUpdateRequest) -> Postmortem | None:
        """Update an existing postmortem."""
        postmortem = await self.get_by_incident(incident_id)
        if not postmortem:
            return None
        update_data = updates.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(postmortem, field, value)
        postmortem.updated_at = datetime.utcnow()
        postmortem.version += 1
        logger.info(
            "postmortem_updated",
            postmortem_id=postmortem.id,
            version=postmortem.version,
        )
        return postmortem

    async def delete(self, incident_id: str) -> bool:
        """Delete a postmortem by incident ID."""
        postmortem_id = self._by_incident.pop(incident_id, None)
        if postmortem_id:
            self._postmortems.pop(postmortem_id, None)
            logger.info(
                "postmortem_deleted",
                postmortem_id=postmortem_id,
                incident_id=incident_id,
            )
            return True
        return False

    async def list(
        self,
        status: PostmortemStatus | None = None,
        service_name: str | None = None,
        limit: int = 100,
    ) -> list[Postmortem]:
        """List postmortems with optional filters."""
        postmortems = list(self._postmortems.values())
        if status:
            postmortems = [p for p in postmortems if p.status == status]
        if service_name:
            postmortems = [p for p in postmortems if p.service_name == service_name]
        postmortems.sort(key=lambda p: p.created_at, reverse=True)
        return postmortems[:limit]

    async def clear(self):
        """Clear all postmortems (for testing)."""
        self._postmortems.clear()
        self._by_incident.clear()


# Global store instance
postmortem_store = PostmortemStore()
