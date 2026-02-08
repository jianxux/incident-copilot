"""Database module for Incident Copilot.

Provides a unified interface for database operations that can use either:
- Direct PostgreSQL connection (default)
- Supabase client (when SUPABASE_DB_ENABLED=true)
"""

from .supabase_db import (
    SupabaseDB,
    get_db,
)

__all__ = ["SupabaseDB", "get_db"]
