"""PagerDuty incident sync helpers shared by web routes."""

import asyncio
import time
import uuid
from datetime import UTC, datetime

import structlog

from ..models import Severity

logger = structlog.get_logger()

# Background PagerDuty auto-sync: track last sync time per tenant (epoch seconds)
_pd_sync_timestamps: dict[str, float] = {}
_PD_SYNC_INTERVAL = 300  # seconds (5 minutes)


def _pd_id_to_uuid(pd_id: str) -> str:
    """Convert a PagerDuty incident ID to a deterministic UUID5.

    Same PD ID always produces the same UUID, so upserts work correctly.
    """
    pd_namespace = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    return str(uuid.uuid5(pd_namespace, pd_id))


def _parse_iso_datetime(
    value: object,
    fallback: datetime | None = None,
    tenant_id: str | None = None,
) -> datetime | None:
    """Parse ISO-ish datetime values and normalize to UTC."""
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    if isinstance(value, str):
        raw = value.strip()
        if raw:
            normalized = raw.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
                return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError as exc:
                logger.warning(
                    "pd_parse_datetime_iso_failed",
                    tenant_id=tenant_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
            try:
                return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except ValueError as exc:
                logger.warning(
                    "pd_parse_datetime_compact_failed",
                    tenant_id=tenant_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

    return fallback


def _build_pd_upsert_rows(
    pd_incidents: list[dict], tenant_id: str
) -> tuple[list[dict], list[dict]]:
    """Convert PagerDuty API incidents into DB upsert rows + summary list.

    Returns (rows_for_db, incident_summaries).
    """
    now_iso = datetime.now(UTC).isoformat()
    rows = []
    summaries = []

    for inc in pd_incidents:
        inc_id = inc.get("id", "")
        if not inc_id:
            continue

        urgency = inc.get("urgency", "low")
        severity_val = Severity.HIGH.value if urgency == "high" else Severity.LOW.value

        service_summary = ""
        svc = inc.get("service")
        if isinstance(svc, dict):
            service_summary = svc.get("summary", "")

        triggered_at = _parse_iso_datetime(
            inc.get("created_at"), datetime.now(UTC), tenant_id=tenant_id
        )
        if triggered_at is None:
            triggered_at = datetime.now(UTC)

        assigned_to = []
        for assignment in inc.get("assignments", []):
            assignee = assignment.get("assignee", {})
            if isinstance(assignee, dict) and assignee.get("summary"):
                assigned_to.append(assignee["summary"])

        ep = inc.get("escalation_policy", {})
        ep_summary = ep.get("summary", "") if isinstance(ep, dict) else ""

        pd_status = inc.get("status", "triggered")
        if pd_status == "resolved":
            db_status = "resolved"
        elif pd_status == "acknowledged":
            db_status = "acknowledged"
        else:
            db_status = "triggered"

        metadata = {
            "provider": "pagerduty",
            "status": pd_status,
            "urgency": urgency,
            "assigned_to": assigned_to,
            "escalation_policy": ep_summary,
        }

        row = {
            "id": _pd_id_to_uuid(inc_id),
            "tenant_id": tenant_id,
            "title": inc.get("title", ""),
            "description": inc.get("description", ""),
            "service": service_summary,
            "severity": severity_val,
            "status": db_status,
            "triggered_at": triggered_at.isoformat(),
            "source": "pagerduty",
            "source_url": inc.get("html_url", ""),
            "source_id": inc_id,
            "metadata": metadata,
            "created_at": triggered_at.isoformat(),
            "updated_at": now_iso,
        }

        if pd_status == "acknowledged":
            acknowledged_dt = _parse_iso_datetime(
                inc.get("last_status_change_at"), datetime.now(UTC), tenant_id=tenant_id
            )
            if acknowledged_dt is None:
                acknowledged_dt = datetime.now(UTC)
            metadata["acknowledged_at"] = acknowledged_dt.isoformat()

        if pd_status == "resolved":
            resolved_dt = _parse_iso_datetime(
                inc.get("last_status_change_at"),
                _parse_iso_datetime(
                    inc.get("resolved_at"), datetime.now(UTC), tenant_id=tenant_id
                ),
                tenant_id=tenant_id,
            )
            if resolved_dt is None:
                resolved_dt = datetime.now(UTC)
            resolved_iso = resolved_dt.isoformat()
            row["resolved_at"] = resolved_iso
            row["processed_at"] = resolved_iso
            metadata["resolved_at"] = resolved_iso

        rows.append(row)

        summaries.append(
            {
                "id": inc_id,
                "title": inc.get("title", ""),
                "status": pd_status,
            }
        )

    return rows, summaries


async def _background_pd_sync(tenant_id: str) -> None:
    """Fire-and-forget background sync of PagerDuty incidents for a tenant."""
    try:
        # 1. Resolve PD token (oauth_token_store then integration_configs)
        oauth_token = ""
        api_key = ""

        try:
            from ..integrations.oauth_tokens import oauth_token_store

            token_rec = await oauth_token_store.get_token(tenant_id, "pagerduty")
            if token_rec and token_rec.access_token:
                oauth_token = token_rec.access_token
                logger.info("pd_sync_token_from_oauth_store", tenant_id=tenant_id)
            else:
                logger.info("pd_sync_no_token_in_oauth_store", tenant_id=tenant_id)
        except Exception as exc:
            logger.warning(
                "pd_sync_oauth_store_error",
                tenant_id=tenant_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )

        if not oauth_token:
            try:
                from ..db.supabase_db import get_db
                from ..security.crypto import decrypt_json

                db = get_db(use_admin=True)
                rows = db.client.table("integration_configs").select("config").eq(
                    "tenant_id", tenant_id
                ).eq("type", "pagerduty").eq("is_active", True).limit(1).execute()

                if rows.data:
                    config = rows.data[0].get("config", {})
                    encrypted = config.get("encrypted", "") if isinstance(config, dict) else ""
                    if encrypted:
                        decrypted = decrypt_json(encrypted)
                        oauth = decrypted.get("oauth", {})
                        oauth_token = oauth.get("access_token", "")
                        api_key = decrypted.get("api_key", "")
                        logger.info(
                            "pd_sync_token_from_integration_configs",
                            tenant_id=tenant_id,
                            has_oauth=bool(oauth_token),
                            has_api_key=bool(api_key),
                        )
                    else:
                        logger.info("pd_sync_no_encrypted_config", tenant_id=tenant_id)
                else:
                    logger.info("pd_sync_no_integration_config_row", tenant_id=tenant_id)
            except Exception as exc:
                logger.warning(
                    "pd_sync_integration_configs_error",
                    tenant_id=tenant_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        token = oauth_token or api_key
        if not token:
            logger.warning("pd_sync_no_token_found", tenant_id=tenant_id)
            return

        pd_auth = f"Bearer {oauth_token}" if oauth_token else f"Token token={api_key}"

        # 2. Fetch last 25 incidents from PagerDuty
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
                logger.warning("bg_pd_sync_api_error", status=resp.status_code, tenant_id=tenant_id)
                return

            pd_incidents = resp.json().get("incidents", [])

        # 3. Batch-upsert all incidents in a single DB call
        rows, _ = _build_pd_upsert_rows(pd_incidents, tenant_id)

        if rows:
            from ..db.supabase_db import get_db

            db = get_db(use_admin=True)

            def _batch_upsert():
                return db.client.table("incidents").upsert(rows, on_conflict="id").execute()

            await db._to_thread(_batch_upsert)

        # 4. Update timestamp on success
        _pd_sync_timestamps[tenant_id] = time.time()
        logger.info("bg_pd_sync_complete", tenant_id=tenant_id, synced=len(pd_incidents))

    except Exception as exc:
        logger.warning(
            "bg_pd_sync_failed",
            tenant_id=tenant_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )


async def _maybe_trigger_pd_sync(tenant_id: str) -> bool:
    """Sync PD incidents if stale. Returns True if sync was awaited (first time)."""
    now = time.time()
    last = _pd_sync_timestamps.get(tenant_id, 0)
    if now - last < _PD_SYNC_INTERVAL:
        return False

    first_sync = last == 0  # Never synced before for this tenant
    # Mark immediately to prevent duplicate launches
    _pd_sync_timestamps[tenant_id] = now

    if first_sync:
        # First sync: await with a timeout so we don't block too long
        try:
            await asyncio.wait_for(_background_pd_sync(tenant_id), timeout=10.0)
        except asyncio.TimeoutError as exc:
            logger.warning(
                "pd_first_sync_timeout",
                tenant_id=tenant_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
        return True

    # Subsequent syncs: fire-and-forget
    asyncio.create_task(_background_pd_sync(tenant_id))
    return False


async def maybe_trigger_pd_sync(tenant_id: str) -> bool:
    """Public wrapper for conditional PagerDuty sync."""
    return await _maybe_trigger_pd_sync(tenant_id)


async def trigger_pd_sync_best_effort(tenant_id: str) -> bool:
    """Trigger conditional sync and never raise exceptions to callers."""
    try:
        return await maybe_trigger_pd_sync(tenant_id)
    except Exception as exc:
        logger.warning(
            "pd_trigger_best_effort_failed",
            tenant_id=tenant_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return False


def trigger_manual_pd_sync(tenant_id: str) -> None:
    """Fire-and-forget explicit PagerDuty sync."""
    try:
        asyncio.create_task(_background_pd_sync(tenant_id))
    except Exception as exc:
        logger.warning(
            "pd_manual_trigger_failed",
            tenant_id=tenant_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
