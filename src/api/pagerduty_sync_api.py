"""PagerDuty sync control/status endpoints."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth.middleware import AuthContext, get_auth_context
from ..integrations.pagerduty_sync import (
    _PD_SYNC_INTERVAL,
    _pd_sync_timestamps,
    trigger_manual_pd_sync,
)

router = APIRouter(prefix="/api/integrations/pagerduty", tags=["integrations-pagerduty"])

_STALE_SECONDS = 600


async def _require_tenant(auth: AuthContext) -> str:
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="auth_required",
        )
    return auth.tenant_id


@router.get("/sync-status")
async def get_sync_status(auth: AuthContext = Depends(get_auth_context)):
    tenant_id = await _require_tenant(auth)

    last_sync_ts = _pd_sync_timestamps.get(tenant_id)
    if not last_sync_ts:
        return {
            "last_sync_at": None,
            "status": "never",
            "interval_seconds": _PD_SYNC_INTERVAL,
        }

    age_seconds = time.time() - float(last_sync_ts)
    sync_status = "stale" if age_seconds > _STALE_SECONDS else "synced"

    return {
        "last_sync_at": datetime.fromtimestamp(last_sync_ts, tz=UTC).isoformat(),
        "status": sync_status,
        "interval_seconds": _PD_SYNC_INTERVAL,
    }


@router.post("/sync")
async def trigger_sync(auth: AuthContext = Depends(get_auth_context)):
    tenant_id = await _require_tenant(auth)
    trigger_manual_pd_sync(tenant_id)
    return {"ok": True, "message": "sync triggered"}
