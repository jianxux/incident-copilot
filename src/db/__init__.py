"""Database layer for Incident Copilot.

Provides Supabase-backed persistence as an alternative to in-memory stores.
Enable with SUPABASE_DB_ENABLED=true.
"""

from .supabase_db import SupabaseDB, get_db

__all__ = ["SupabaseDB", "get_db"]
