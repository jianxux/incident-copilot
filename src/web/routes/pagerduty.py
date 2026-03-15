"""PagerDuty sync endpoints."""

from fastapi import Depends, HTTPException

from ...auth.middleware import AuthContext, get_auth_context
from ...integrations.pagerduty_sync import _build_pd_upsert_rows
from .common import logger, router


@router.post("/api/integrations/pagerduty/sync")
async def sync_pagerduty_incidents(
    auth: AuthContext = Depends(get_auth_context),
):
    """Pull recent incidents from PagerDuty and persist to incident store."""
    tenant_id = auth.tenant_id or "default"

    try:
        # Resolve PagerDuty token - same pattern as import_pagerduty_services
        from ...integrations.oauth_tokens import oauth_token_store

        token_rec = await oauth_token_store.get_token(tenant_id, "pagerduty")
        oauth_token = ""
        api_key = ""

        if token_rec and token_rec.access_token:
            oauth_token = token_rec.access_token
        else:
            try:
                from ...db.supabase_db import get_db
                from ...security.crypto import decrypt_json

                db = get_db(use_admin=True)
                rows = (
                    db.client.table("integration_configs")
                    .select("config")
                    .eq("tenant_id", tenant_id)
                    .eq("type", "pagerduty")
                    .eq("is_active", True)
                    .limit(1)
                    .execute()
                )

                if rows.data:
                    config = rows.data[0].get("config", {})
                    encrypted = (
                        config.get("encrypted", "") if isinstance(config, dict) else ""
                    )
                    if encrypted:
                        decrypted = decrypt_json(encrypted)
                        oauth = decrypted.get("oauth", {})
                        oauth_token = oauth.get("access_token", "")
                        api_key = decrypted.get("api_key", "")
            except Exception as exc:
                logger.warning("sync_incidents_legacy_lookup_failed", error=str(exc))

        token = oauth_token or api_key
        if not token:
            raise HTTPException(status_code=404, detail="PagerDuty not connected")

        if oauth_token:
            pd_auth = f"Bearer {oauth_token}"
        else:
            pd_auth = f"Token token={api_key}"

        # Fetch recent incidents from PagerDuty API
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.pagerduty.com/incidents",
                headers={
                    "Authorization": pd_auth,
                    "Content-Type": "application/json",
                    "Accept": "application/vnd.pagerduty+json;version=2",
                },
                params={
                    "statuses[]": ["triggered", "acknowledged", "resolved"],
                    "sort_by": "created_at:desc",
                    "limit": 25,
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "sync_pd_incidents_api_error",
                    status=resp.status_code,
                    body=resp.text[:500],
                )
                return {
                    "ok": False,
                    "error": f"PagerDuty API returned {resp.status_code}",
                    "details": resp.text[:200],
                }

            pd_incidents = resp.json().get("incidents", [])

        rows, incident_summaries = _build_pd_upsert_rows(pd_incidents, tenant_id)

        if rows:
            from ...db.supabase_db import get_db

            db = get_db(use_admin=True)

            def _batch_upsert():
                return (
                    db.client.table("incidents")
                    .upsert(rows, on_conflict="id")
                    .execute()
                )

            await db._to_thread(_batch_upsert)

        return {"ok": True, "synced": len(rows), "incidents": incident_summaries}

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "sync_pagerduty_incidents_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {"ok": False, "error": str(exc)}


@router.get("/api/integrations/pagerduty/sync/status")
async def pagerduty_sync_status(
    auth: AuthContext = Depends(get_auth_context),
):
    """Return PagerDuty sync connection status."""
    tenant_id = auth.tenant_id or "default"

    connected = False
    try:
        from ...integrations.oauth_tokens import oauth_token_store

        token_rec = await oauth_token_store.get_token(tenant_id, "pagerduty")
        if token_rec and token_rec.access_token:
            connected = True
    except Exception:
        pass

    if not connected:
        try:
            from ...db.supabase_db import get_db
            from ...security.crypto import decrypt_json

            db = get_db(use_admin=True)
            rows = (
                db.client.table("integration_configs")
                .select("config")
                .eq("tenant_id", tenant_id)
                .eq("type", "pagerduty")
                .eq("is_active", True)
                .limit(1)
                .execute()
            )

            if rows.data:
                config = rows.data[0].get("config", {})
                encrypted = (
                    config.get("encrypted", "") if isinstance(config, dict) else ""
                )
                if encrypted:
                    decrypted = decrypt_json(encrypted)
                    oauth = decrypted.get("oauth", {})
                    if oauth.get("access_token") or decrypted.get("api_key"):
                        connected = True
        except Exception:
            pass

    return {"connected": connected, "last_sync": None}
