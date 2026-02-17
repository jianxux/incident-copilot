"""Compatibility shim: OAuth integration routes live in src.api.oauth_integrations."""

from src.api.oauth_integrations import router

__all__ = ["router"]
