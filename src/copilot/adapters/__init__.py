"""Channel adapters for Copilot."""

from .slack_adapter import router as slack_adapter_router
from .teams_adapter import router as teams_adapter_router
from .web_adapter import router as web_adapter_router

__all__ = ["slack_adapter_router", "teams_adapter_router", "web_adapter_router"]
