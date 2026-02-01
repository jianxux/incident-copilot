"""Web dashboard module for Incident Copilot."""

from .routes import landing_router, router as web_router
from .store import incident_store

__all__ = ["web_router", "landing_router", "incident_store"]
