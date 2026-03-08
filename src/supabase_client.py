"""Supabase client singleton for Incident Copilot."""

import structlog

from supabase import Client, create_client

from .config import get_settings

logger = structlog.get_logger()

_client: Client | None = None


def get_supabase_client() -> Client | None:
    """Get the Supabase client singleton.

    Returns:
        Supabase client if configured, None otherwise.
    """
    global _client

    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_anon_key:
        return None

    if _client is None:
        _client = create_client(
            settings.supabase_url,
            settings.supabase_anon_key,
        )
        logger.info("supabase_client_initialized", url=settings.supabase_url)

    return _client


def get_supabase_admin_client() -> Client | None:
    """Get the Supabase admin client (with service role key).

    Use this for server-side operations that need elevated permissions.

    Returns:
        Supabase admin client if configured, None otherwise.
    """
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None

    # Admin client is not cached to avoid permission leaks
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )


def is_supabase_configured() -> bool:
    """Check if Supabase is properly configured."""
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_anon_key)


def is_supabase_auth_enabled() -> bool:
    """Check if Supabase Auth is enabled."""
    settings = get_settings()
    return bool(
        settings.supabase_auth_enabled
        and is_supabase_configured()
        and settings.supabase_service_role_key
    )


def is_supabase_db_enabled() -> bool:
    """Check if Supabase database is enabled."""
    settings = get_settings()
    return bool(settings.supabase_db_enabled and is_supabase_configured())
