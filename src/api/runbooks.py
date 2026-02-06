"""Runbook API endpoints.

This module re-exports the runbook routes from src.runbooks.routes,
which includes:
- Runbook search and indexing
- Runbook execution management
- Progress tracking
- AI-powered suggestions
"""

# Import the router from the runbooks module
from ..runbooks.routes import router

__all__ = ["router"]
