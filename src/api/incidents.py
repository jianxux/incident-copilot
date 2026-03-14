"""Tenant-scoped incidents REST API for the frontend dashboard."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ..auth.middleware import AuthContext, get_auth_context
from ..config import get_settings
from ..integrations import GitHubAdapter
from ..integrations.github import resolve_github_creds
from ..models import Severity
from ..supabase_client import is_supabase_db_enabled
from ..web.store import incident_store

logger = structlog.get_logger()

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

# In-memory fallback for tests/dev when Supabase DB is disabled.
_IN_MEMORY_NOTES: dict[str, list[dict[str, Any]]] = {}
_IN_MEMORY_TIMELINE: dict[str, list[dict[str, Any]]] = {}

_ALLOWED_SEVERITIES = {"critical", "high", "medium", "low", "info"}
_ALLOWED_STATUSES = {"triggered", "acknowledged", "resolved", "processing", "error"}

_STATUS_DB_TO_API = {
    "completed": "resolved",
    "error": "error",
}

_STATUS_API_TO_DB = {
    "triggered": {"triggered"},
    "acknowledged": {"acknowledged"},
    "resolved": {"resolved", "completed"},
    "processing": {"processing"},
    "error": {"error"},
}

GitHubStatus = Literal["connected", "no_credentials", "no_repo_mapping", "enriched"]


class ResolveRequest(BaseModel):
    resolution: str | None = Field(default=None, max_length=5000)


class NoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
    return None


def _iso(value: Any) -> str | None:
    dt = _as_datetime(value)
    return dt.isoformat() if dt else None


def _normalize_status(value: Any) -> str:
    raw = (str(value or "processing")).lower()
    mapped = _STATUS_DB_TO_API.get(raw, raw)
    return mapped if mapped in _ALLOWED_STATUSES else "processing"


def _normalize_severity(value: Any) -> str:
    raw = (str(value or Severity.MEDIUM.value)).lower()
    return raw if raw in _ALLOWED_SEVERITIES else Severity.MEDIUM.value


def _parse_multi_values(raw_values: Iterable[str] | None) -> list[str]:
    if not raw_values:
        return []
    parsed: list[str] = []
    for value in raw_values:
        for token in value.split(","):
            normalized = token.strip()
            if normalized:
                parsed.append(normalized)
    return parsed


def _extract_multi_query(
    request: Request, key: str, value: list[str] | None
) -> list[str]:
    values: list[str] = []
    if value:
        values.extend(value)
    values.extend(request.query_params.getlist(key))
    values.extend(request.query_params.getlist(f"{key}[]"))
    return _parse_multi_values(values)


def _has_memory_tenant_assignments() -> bool:
    """Return True when the in-memory incident store has explicit tenant scoping."""
    for candidate in (incident_store, getattr(incident_store, "_memory", None)):
        tenant_map = getattr(candidate, "_tenant_map", None)
        if isinstance(tenant_map, dict) and tenant_map:
            return True
    return False


def _compute_duration_ms(start: Any, end: Any) -> int | None:
    start_dt = _as_datetime(start)
    end_dt = _as_datetime(end)
    if not start_dt or not end_dt:
        return None
    return max(0, int((end_dt - start_dt).total_seconds() * 1000))


def _compute_duration_seconds(start: Any, end: Any) -> int | None:
    start_dt = _as_datetime(start)
    end_dt = _as_datetime(end)
    if not start_dt or not end_dt:
        return None
    return max(0, int((end_dt - start_dt).total_seconds()))


def _extract_verdict_summary(row: dict[str, Any]) -> str | None:
    metadata = _extract_metadata(row)
    verdict = metadata.get("verdict") or metadata.get("ai_verdict") or {}
    if isinstance(verdict, dict):
        return verdict.get("summary") or verdict.get("one_liner")
    if isinstance(verdict, str):
        return verdict[:200]
    return None


def _extract_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _format_incident(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _extract_metadata(row)

    created_at = _iso(row.get("triggered_at") or row.get("created_at")) or _now_iso()
    acknowledged_at = _iso(
        row.get("acknowledged_at") or metadata.get("acknowledged_at")
    )
    resolved_at = _iso(
        row.get("resolved_at") or row.get("processed_at") or metadata.get("resolved_at")
    )

    tta = _compute_duration_ms(created_at, acknowledged_at)
    ttr = _compute_duration_ms(created_at, resolved_at)

    processed_at = _iso(row.get("processed_at"))
    triggered_at = _iso(row.get("triggered_at")) or created_at

    incident = {
        "id": str(row.get("id", "")),
        "incident_id": str(row.get("id", "")),
        "title": row.get("title") or "Untitled incident",
        "description": row.get("description"),
        "severity": _normalize_severity(row.get("severity")),
        "status": _normalize_status(row.get("status")),
        "source": row.get("source") or "manual",
        "service": row.get("service") or "unknown",
        "service_name": row.get("service") or "unknown",
        "assignee": metadata.get("assignee") or row.get("assigned_to"),
        "team": metadata.get("team"),
        "created_at": created_at,
        "updated_at": _iso(row.get("updated_at")) or created_at,
        "triggered_at": triggered_at,
        "processed_at": processed_at,
        "acknowledged_at": acknowledged_at,
        "resolved_at": resolved_at,
        "duration_seconds": _compute_duration_seconds(
            row.get("triggered_at") or row.get("created_at"),
            row.get("processed_at") or row.get("resolved_at"),
        ),
        "verdict_summary": _extract_verdict_summary(row),
        "source_url": row.get("source_url") or "",
        "ttd": metadata.get("ttd") if isinstance(metadata.get("ttd"), int) else None,
        "tta": tta,
        "ttr": ttr,
        "tags": metadata.get("tags") if isinstance(metadata.get("tags"), list) else [],
        "labels": (
            metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
        ),
        "related_incidents": (
            metadata.get("related_incidents")
            if isinstance(metadata.get("related_incidents"), list)
            else []
        ),
        "runbooks": (
            metadata.get("runbooks")
            if isinstance(metadata.get("runbooks"), list)
            else []
        ),
        "context": (
            metadata.get("context")
            if isinstance(metadata.get("context"), dict)
            else None
        ),
    }
    return incident


def _map_context_payload(
    incident_id: str,
    payload: dict[str, Any] | None,
    context_id: str | None = None,
    created_at: Any = None,
    github_status: GitHubStatus | None = None,
) -> dict[str, Any]:
    data = dict(payload or {})

    if "github_context" not in data and isinstance(data.get("github"), dict):
        data["github_context"] = data.get("github")
    if "datadog_context" not in data and isinstance(data.get("datadog"), dict):
        data["datadog_context"] = data.get("datadog")
    if "on_call" not in data and isinstance(data.get("oncall"), dict):
        data["on_call"] = data.get("oncall")

    data["id"] = str(context_id or data.get("id") or "")
    data["incident_id"] = incident_id
    data["created_at"] = _iso(created_at or data.get("created_at")) or _now_iso()
    if github_status is not None:
        data["github_status"] = github_status

    return data


def _service_has_repo_mapping(adapter: GitHubAdapter, service_name: str) -> bool:
    return service_name in adapter.service_repo_map


async def _get_github_enrichment_prereqs(
    service: str,
    tenant_id: str | None,
) -> tuple[GitHubStatus, GitHubAdapter | None]:
    settings = get_settings()
    token, org = await resolve_github_creds(tenant_id)
    if not token:
        logger.warning(
            "ondemand_github_enrichment_skipped",
            reason="no_token",
            tenant_id=tenant_id,
            service=service,
        )
        return "no_credentials", None

    adapter = GitHubAdapter.from_credentials(token, org, settings)
    if not adapter._get_repo_for_service(service):
        reason = (
            "no_org"
            if not org and not _service_has_repo_mapping(adapter, service)
            else "no_repo_mapping"
        )
        logger.warning(
            "ondemand_github_enrichment_skipped",
            reason=reason,
            tenant_id=tenant_id,
            service=service,
            has_org=bool(org),
            has_service_mapping=_service_has_repo_mapping(adapter, service),
        )
        return "no_repo_mapping", adapter

    return "connected", adapter


async def _get_github_status(
    incident_row: dict[str, Any],
    tenant_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> GitHubStatus:
    github_context = _extract_github_context(payload)
    if github_context:
        return "enriched"

    service = incident_row.get("service") or incident_row.get("service_name")
    if not service:
        return "no_repo_mapping"

    status, _adapter = await _get_github_enrichment_prereqs(service, tenant_id)
    return status


async def _try_ondemand_enrichment(
    incident_row: dict[str, Any],
    tenant_id: str | None = None,
) -> dict[str, Any]:
    service = incident_row.get("service") or incident_row.get("service_name")
    if not service:
        logger.warning(
            "ondemand_github_enrichment_skipped",
            reason="no_service",
            tenant_id=tenant_id,
            incident_id=incident_row.get("id"),
        )
        return {}

    status, adapter = await _get_github_enrichment_prereqs(service, tenant_id)
    if not adapter or status != "connected":
        return {}

    try:
        github_context = await adapter.get_context(service)
        if not github_context:
            logger.warning(
                "ondemand_github_enrichment_skipped",
                reason=adapter.last_context_error_reason or "api_error",
                tenant_id=tenant_id,
                incident_id=incident_row.get("id"),
                service=service,
            )
            return {}

        payload = github_context.model_dump(mode="json")
        return {"github": payload, "github_context": payload}
    except Exception as exc:
        logger.warning(
            "ondemand_github_enrichment_failed",
            error=str(exc),
            incident_id=incident_row.get("id"),
            service=service,
            tenant_id=tenant_id,
            reason="api_error",
        )
        return {}


def _event_to_timeline(event: dict[str, Any], incident_id: str) -> dict[str, Any]:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        metadata = event.get("data") if isinstance(event.get("data"), dict) else {}

    description = (
        event.get("description")
        or event.get("title")
        or event.get("message")
        or "Incident event"
    )

    return {
        "id": str(event.get("id", "")),
        "incident_id": incident_id,
        "type": str(event.get("event_type") or "comment"),
        "description": description,
        "actor": event.get("actor") or metadata.get("actor"),
        "timestamp": _iso(event.get("occurred_at") or event.get("created_at"))
        or _now_iso(),
        "metadata": metadata,
    }


def _extract_github_context(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    github_context = payload.get("github_context")
    if isinstance(github_context, dict):
        return github_context

    github = payload.get("github")
    if isinstance(github, dict):
        return github

    if any(
        key in payload for key in ("recent_deploys", "recent_prs", "recent_deployments")
    ):
        return payload

    return {}


def _build_github_timeline_events(
    incident_id: str,
    github_context: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for idx, deploy in enumerate(github_context.get("recent_deploys") or []):
        if not isinstance(deploy, dict):
            continue
        timestamp = _iso(deploy.get("timestamp")) or _now_iso()
        short_sha = str(deploy.get("short_sha") or "")[:12]
        message = deploy.get("message") or "Code change"
        description = f"{short_sha}: {message}" if short_sha else str(message)
        events.append(
            {
                "id": f"{incident_id}-gh-code-{idx}",
                "incident_id": incident_id,
                "type": "code_change",
                "description": description,
                "actor": deploy.get("author"),
                "timestamp": timestamp,
                "metadata": {"source": "github", "commit": deploy},
            }
        )

    for idx, pr in enumerate(github_context.get("recent_prs") or []):
        if not isinstance(pr, dict):
            continue
        timestamp = _iso(pr.get("merged_at")) or _now_iso()
        number = pr.get("number")
        title = pr.get("title") or "Pull request merged"
        prefix = f"PR #{number}: " if number is not None else "PR: "
        events.append(
            {
                "id": f"{incident_id}-gh-pr-{idx}",
                "incident_id": incident_id,
                "type": "pull_request",
                "description": f"{prefix}{title}",
                "actor": pr.get("author"),
                "timestamp": timestamp,
                "metadata": {"source": "github", "pull_request": pr},
            }
        )

    for idx, deployment in enumerate(github_context.get("recent_deployments") or []):
        if not isinstance(deployment, dict):
            continue
        timestamp = _iso(deployment.get("created_at")) or _now_iso()
        environment = deployment.get("environment") or "unknown"
        status = deployment.get("status") or "unknown"
        events.append(
            {
                "id": f"{incident_id}-gh-deploy-{idx}",
                "incident_id": incident_id,
                "type": "deployment",
                "description": f"Deployment to {environment} ({status})",
                "actor": deployment.get("creator"),
                "timestamp": timestamp,
                "metadata": {"source": "github", "deployment": deployment},
            }
        )

    return events


async def _github_timeline_events_from_context(
    incident_id: str,
    *,
    incident_row: dict[str, Any] | None,
    stored_context_payload: dict[str, Any] | None,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    github_context = _extract_github_context(stored_context_payload)
    if not github_context and incident_row:
        enriched_payload = await _try_ondemand_enrichment(
            incident_row, tenant_id=tenant_id
        )
        github_context = _extract_github_context(enriched_payload)

    if not github_context:
        return []

    return _build_github_timeline_events(incident_id, github_context)


async def _require_tenant(auth: AuthContext) -> str:
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="auth_required",
        )
    return auth.tenant_id


async def _trigger_pd_sync_best_effort(tenant_id: str) -> None:
    from src.integrations.pagerduty_sync import trigger_pd_sync_best_effort as _pd_sync

    await _pd_sync(tenant_id)


async def _force_pd_sync_best_effort(tenant_id: str) -> bool:
    from src.integrations.pagerduty_sync import (
        force_pd_sync_best_effort as _pd_force_sync,
    )

    return await _pd_force_sync(tenant_id)


def _get_pd_sync_status(tenant_id: str) -> dict[str, Any]:
    from src.integrations.pagerduty_sync import get_pd_sync_status as _pd_sync_status

    return _pd_sync_status(tenant_id)


def _derive_pd_sync_state(status_data: dict[str, Any]) -> str:
    if bool(status_data.get("in_progress")):
        return "in_progress"

    attempt_dt = _as_datetime(status_data.get("last_attempt"))
    success_dt = _as_datetime(status_data.get("last_success"))
    last_error = status_data.get("last_error")

    if attempt_dt is None:
        return "never"
    if isinstance(last_error, str) and (success_dt is None or attempt_dt >= success_dt):
        return "error"
    if success_dt and (datetime.now(UTC) - success_dt) > timedelta(seconds=600):
        return "stale"
    return "synced"


async def _capture_resolution_memory_best_effort(
    *,
    incident: dict[str, Any],
    resolution: str | None,
    resolved_at: str,
) -> None:
    """Capture incident resolution to memory; never raise into API flow."""
    try:
        from ..orchestrator import ContextOrchestrator

        orchestrator = ContextOrchestrator(get_settings())
        await orchestrator.capture_resolution(
            incident=incident,
            resolution=resolution,
            resolved_at=resolved_at,
        )
    except Exception as exc:
        logger.warning(
            "resolution_memory_capture_best_effort_failed",
            incident_id=incident.get("id") or incident.get("incident_id"),
            error=str(exc),
        )


async def _get_incident_row(tenant_id: str, incident_id: str) -> dict[str, Any] | None:
    from ..db.supabase_db import get_db

    db = get_db(use_admin=True)
    return await db.get_processing_incident(
        tenant_id=tenant_id, incident_id=incident_id
    )


async def _update_incident_row(
    tenant_id: str,
    incident_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    from ..db.supabase_db import get_db

    db = get_db(use_admin=True)
    updates["updated_at"] = _now_iso()

    def _do_update():
        return (
            db.client.table("incidents")
            .update(updates)
            .eq("id", incident_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )

    result = await db._to_thread(_do_update)
    if result.data:
        return result.data[0]
    return await db.get_processing_incident(
        tenant_id=tenant_id, incident_id=incident_id
    )


async def _list_supabase_incidents(
    *,
    tenant_id: str,
    page: int,
    limit: int,
    statuses: list[str],
    severities: list[str],
    services: list[str],
    teams: list[str],
    assignee: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    search: str | None,
) -> tuple[list[dict[str, Any]], int]:
    from ..db.supabase_db import get_db

    db = get_db(use_admin=True)

    def _build_query(include_range: bool):
        query = (
            db.client.table("incidents")
            .select("*", count="exact")
            .eq("tenant_id", tenant_id)
        )

        if statuses:
            db_statuses: set[str] = set()
            for s in statuses:
                db_statuses.update(_STATUS_API_TO_DB.get(s, {s}))
            query = query.in_("status", list(db_statuses))

        if severities:
            query = query.in_("severity", severities)

        if services:
            query = query.in_("service", services)

        if date_from:
            query = query.gte("created_at", date_from.isoformat())

        if date_to:
            # Inclusive end-of-day behavior when a date string is passed by frontend.
            date_to_end = date_to + timedelta(days=1)
            query = query.lt("created_at", date_to_end.isoformat())

        if search:
            escaped = search.replace('"', "")
            query = query.or_(
                f"title.ilike.%{escaped}%,description.ilike.%{escaped}%,service.ilike.%{escaped}%"
            )

        query = query.order("created_at", desc=True)

        if include_range:
            offset = (page - 1) * limit
            query = query.range(offset, offset + limit - 1)

        return query

    page_result = await db._to_thread(lambda: _build_query(True).execute())
    total = int(page_result.count or 0)
    rows: list[dict[str, Any]] = list(page_result.data or [])

    if teams or assignee:
        # team/assignee are metadata-driven in current schema; apply in Python.
        def _matches(row: dict[str, Any]) -> bool:
            metadata = _extract_metadata(row)
            row_team = metadata.get("team")
            row_assignee = metadata.get("assignee") or row.get("assigned_to")
            if teams and row_team not in teams:
                return False
            if assignee and str(row_assignee or "") != assignee:
                return False
            return True

        all_rows = await db._to_thread(lambda: _build_query(False).execute())
        filtered = [r for r in (all_rows.data or []) if _matches(r)]
        total = len(filtered)
        offset = (page - 1) * limit
        rows = filtered[offset : offset + limit]

    return rows, total


def _list_inmemory_incidents(
    rows: list[dict[str, Any]],
    *,
    page: int,
    limit: int,
    statuses: list[str],
    severities: list[str],
    services: list[str],
    teams: list[str],
    assignee: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    search: str | None,
) -> tuple[list[dict[str, Any]], int]:
    def _matches(row: dict[str, Any]) -> bool:
        metadata = _extract_metadata(row)

        if statuses and _normalize_status(row.get("status")) not in statuses:
            return False
        if severities and _normalize_severity(row.get("severity")) not in severities:
            return False
        if services and (row.get("service") or "unknown") not in services:
            return False

        row_team = metadata.get("team")
        if teams and row_team not in teams:
            return False

        row_assignee = metadata.get("assignee") or row.get("assigned_to")
        if assignee and str(row_assignee or "") != assignee:
            return False

        created_at = _as_datetime(row.get("created_at") or row.get("triggered_at"))
        if date_from and created_at and created_at < date_from:
            return False
        if date_to and created_at and created_at >= (date_to + timedelta(days=1)):
            return False

        if search:
            text = " ".join(
                [
                    str(row.get("title") or ""),
                    str(row.get("description") or ""),
                    str(row.get("service") or ""),
                ]
            ).lower()
            if search.lower() not in text:
                return False

        return True

    filtered = [row for row in rows if _matches(row)]
    total = len(filtered)
    offset = (page - 1) * limit
    return filtered[offset : offset + limit], total


async def _build_timeline_from_inmemory(
    incident_id: str,
    incident: dict[str, Any],
    *,
    incident_row: dict[str, Any] | None = None,
    stored_context_payload: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    events = list(_IN_MEMORY_TIMELINE.get(incident_id, []))

    base_events: list[dict[str, Any]] = [
        {
            "id": f"{incident_id}-created",
            "incident_id": incident_id,
            "event_type": "created",
            "description": "Incident triggered",
            "occurred_at": incident.get("created_at"),
            "metadata": {},
        }
    ]

    if incident.get("acknowledged_at"):
        base_events.append(
            {
                "id": f"{incident_id}-ack",
                "incident_id": incident_id,
                "event_type": "acknowledged",
                "description": "Incident acknowledged",
                "occurred_at": incident.get("acknowledged_at"),
                "metadata": {},
            }
        )

    if incident.get("resolved_at"):
        base_events.append(
            {
                "id": f"{incident_id}-resolved",
                "incident_id": incident_id,
                "event_type": "resolved",
                "description": "Incident resolved",
                "occurred_at": incident.get("resolved_at"),
                "metadata": {},
            }
        )

    combined = base_events + events
    timeline = [_event_to_timeline(event, incident_id) for event in combined]
    timeline.extend(
        await _github_timeline_events_from_context(
            incident_id,
            incident_row=incident_row,
            stored_context_payload=stored_context_payload,
            tenant_id=tenant_id,
        )
    )
    timeline.sort(key=lambda item: item.get("timestamp") or "")
    return timeline


@router.get("")
async def list_incidents(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: list[str] | None = Query(None),
    severity: list[str] | None = Query(None),
    service: list[str] | None = Query(None),
    team: list[str] | None = Query(None),
    assignee: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    search: str | None = Query(None),
    auth: AuthContext = Depends(get_auth_context),
):
    """List incidents with frontend-compatible filters and pagination."""
    tenant_id = auth.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="auth_required")

    # Trigger PagerDuty background sync (batch upsert, non-blocking after first load)
    await _trigger_pd_sync_best_effort(tenant_id)

    statuses = [
        s
        for s in _extract_multi_query(request, "status", status)
        if s in _ALLOWED_STATUSES
    ]
    severities = [
        s
        for s in _extract_multi_query(request, "severity", severity)
        if s in _ALLOWED_SEVERITIES
    ]
    services = _extract_multi_query(request, "service", service)
    teams = _extract_multi_query(request, "team", team)

    parsed_date_from = _as_datetime(date_from)
    parsed_date_to = _as_datetime(date_to)

    def _stored_to_row(item: Any) -> dict[str, Any]:
        return {
            "id": item.incident_id,
            "title": item.title,
            "description": item.description,
            "service": item.service_name,
            "severity": item.severity.value,
            "status": item.status,
            "triggered_at": item.triggered_at,
            "processed_at": item.processed_at,
            "created_at": item.triggered_at,
            "updated_at": item.processed_at or item.triggered_at,
            "metadata": item.metadata if isinstance(item.metadata, dict) else {},
        }

    if is_supabase_db_enabled():
        try:
            supabase_rows, _ = await _list_supabase_incidents(
                tenant_id=tenant_id,
                page=1,
                limit=2000,
                statuses=statuses,
                severities=severities,
                services=services,
                teams=teams,
                assignee=assignee,
                date_from=parsed_date_from,
                date_to=parsed_date_to,
                search=search,
            )
        except Exception as exc:
            logger.warning(
                "list_incidents_supabase_fetch_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                tenant_id=tenant_id,
            )
            supabase_rows = []

        stored = await incident_store.get_all_incidents(tenant_id=tenant_id)
        if not stored and not _has_memory_tenant_assignments():
            stored = await incident_store.get_all_incidents()
        memory_rows = [_stored_to_row(item) for item in stored]

        merged_by_id: dict[str, dict[str, Any]] = {
            str(row.get("id")): row for row in memory_rows if row.get("id")
        }
        for row in supabase_rows:
            row_id = str(row.get("id")) if row.get("id") is not None else ""
            if row_id:
                merged_by_id[row_id] = row  # Supabase wins on conflict.

        merged_rows = list(merged_by_id.values())
        merged_rows.sort(
            key=lambda row: _as_datetime(
                row.get("created_at") or row.get("triggered_at")
            )
            or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

        page_rows, total = _list_inmemory_incidents(
            merged_rows,
            page=page,
            limit=limit,
            statuses=statuses,
            severities=severities,
            services=services,
            teams=teams,
            assignee=assignee,
            date_from=parsed_date_from,
            date_to=parsed_date_to,
            search=search,
        )
        incidents = [_format_incident(row) for row in page_rows]
        return {"incidents": incidents, "total": total}

    stored = await incident_store.get_all_incidents(tenant_id=tenant_id)
    if not stored and not _has_memory_tenant_assignments():
        stored = await incident_store.get_all_incidents()
    rows = [_stored_to_row(item) for item in stored]

    page_rows, total = _list_inmemory_incidents(
        rows,
        page=page,
        limit=limit,
        statuses=statuses,
        severities=severities,
        services=services,
        teams=teams,
        assignee=assignee,
        date_from=parsed_date_from,
        date_to=parsed_date_to,
        search=search,
    )
    incidents = [_format_incident(row) for row in page_rows]
    return {"incidents": incidents, "total": total}


@router.get("/stats")
async def get_incident_stats(
    auth: AuthContext = Depends(get_auth_context),
):
    """Return incident stats summary matching frontend IncidentStats shape."""
    tenant_id = await _require_tenant(auth)

    rows: list[dict[str, Any]]
    if is_supabase_db_enabled():
        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)

        def _do():
            return (
                db.client.table("incidents")
                .select("*")
                .eq("tenant_id", tenant_id)
                .order("created_at", desc=True)
                .limit(2000)
                .execute()
            )

        result = await db._to_thread(_do)
        rows = list(result.data or [])
    else:
        stored = await incident_store.get_all_incidents()
        rows = [
            {
                "id": item.incident_id,
                "title": item.title,
                "service": item.service_name,
                "severity": item.severity.value,
                "status": item.status,
                "triggered_at": item.triggered_at,
                "processed_at": item.processed_at,
                "created_at": item.triggered_at,
                "updated_at": item.processed_at or item.triggered_at,
                "metadata": {},
            }
            for item in stored
        ]

    by_status = {
        "triggered": 0,
        "acknowledged": 0,
        "resolved": 0,
        "processing": 0,
    }
    by_severity = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }

    now = datetime.now(UTC)
    today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    week_start = now - timedelta(days=7)

    tta_values_ms: list[int] = []
    ttr_values_ms: list[int] = []
    incidents_today = 0
    incidents_week = 0

    for row in rows:
        item = _format_incident(row)
        status_value = item.get("status")
        severity_value = item.get("severity")
        if status_value == "error":
            status_value = "processing"
        if status_value in by_status:
            by_status[status_value] += 1
        if severity_value in by_severity:
            by_severity[severity_value] += 1

        created_at = _as_datetime(item.get("created_at"))
        if created_at and created_at >= today_start:
            incidents_today += 1
        if created_at and created_at >= week_start:
            incidents_week += 1

        if isinstance(item.get("tta"), int):
            tta_values_ms.append(int(item["tta"]))
        if isinstance(item.get("ttr"), int):
            ttr_values_ms.append(int(item["ttr"]))

    mtta_minutes = (
        (sum(tta_values_ms) / len(tta_values_ms) / 60000.0) if tta_values_ms else 0.0
    )
    mttr_hours = (
        (sum(ttr_values_ms) / len(ttr_values_ms) / 3600000.0) if ttr_values_ms else 0.0
    )

    return {
        "total": len(rows),
        "by_status": by_status,
        "by_severity": by_severity,
        "mttr_hours": mttr_hours,
        "mtta_minutes": mtta_minutes,
        "incidents_today": incidents_today,
        "incidents_week": incidents_week,
    }


@router.get("/sync-status")
async def get_incident_sync_status(auth: AuthContext = Depends(get_auth_context)):
    """Return PagerDuty sync status for the current tenant."""
    tenant_id = await _require_tenant(auth)
    status_data = _get_pd_sync_status(tenant_id)
    return {
        "last_attempt": (
            status_data.get("last_attempt")
            if isinstance(status_data.get("last_attempt"), str)
            else None
        ),
        "last_success": (
            status_data.get("last_success")
            if isinstance(status_data.get("last_success"), str)
            else None
        ),
        "last_error": (
            status_data.get("last_error")
            if isinstance(status_data.get("last_error"), str)
            else None
        ),
        "status": _derive_pd_sync_state(status_data),
    }


@router.post("/sync")
async def force_incident_sync(auth: AuthContext = Depends(get_auth_context)):
    """Force a PagerDuty sync for the current tenant, bypassing throttle."""
    tenant_id = await _require_tenant(auth)
    ok = await _force_pd_sync_best_effort(tenant_id)
    return {
        "ok": ok,
        "status": _derive_pd_sync_state(_get_pd_sync_status(tenant_id)),
    }


@router.get("/{incident_id}")
async def get_incident_detail(
    incident_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Get incident details by id."""
    tenant_id = await _require_tenant(auth)

    if is_supabase_db_enabled():
        row = await _get_incident_row(tenant_id=tenant_id, incident_id=incident_id)
        if not row:
            raise HTTPException(status_code=404, detail="incident_not_found")
        return _format_incident(row)

    item = await incident_store.get_incident(incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="incident_not_found")

    row = {
        "id": item.incident_id,
        "title": item.title,
        "service": item.service_name,
        "severity": item.severity.value,
        "status": item.status,
        "triggered_at": item.triggered_at,
        "processed_at": item.processed_at,
        "created_at": item.triggered_at,
        "updated_at": item.processed_at or item.triggered_at,
        "metadata": {},
    }
    return _format_incident(row)


@router.post("/{incident_id}/acknowledge")
async def acknowledge_incident(
    incident_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Acknowledge an incident."""
    tenant_id = await _require_tenant(auth)
    actor = auth.user.email if auth.user else "system"
    now = _now_iso()

    if is_supabase_db_enabled():
        row = await _get_incident_row(tenant_id=tenant_id, incident_id=incident_id)
        if not row:
            raise HTTPException(status_code=404, detail="incident_not_found")

        metadata = _extract_metadata(row)
        metadata["acknowledged_at"] = now

        updated = await _update_incident_row(
            tenant_id=tenant_id,
            incident_id=incident_id,
            updates={"status": "acknowledged", "metadata": metadata},
        )

        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        await db.create_incident_event(
            incident_id=incident_id,
            tenant_id=tenant_id,
            event_type="acknowledged",
            title="Incident acknowledged",
            description="Incident acknowledged",
            actor=actor,
            metadata={"actor": actor},
            occurred_at=now,
        )

        return _format_incident(updated or row)

    item = await incident_store.get_incident(incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="incident_not_found")

    item.status = "acknowledged"
    _IN_MEMORY_TIMELINE.setdefault(incident_id, []).append(
        {
            "id": f"{incident_id}-ack-{len(_IN_MEMORY_TIMELINE.get(incident_id, [])) + 1}",
            "incident_id": incident_id,
            "event_type": "acknowledged",
            "description": "Incident acknowledged",
            "actor": actor,
            "occurred_at": now,
            "metadata": {"actor": actor},
        }
    )

    row = {
        "id": item.incident_id,
        "title": item.title,
        "service": item.service_name,
        "severity": item.severity.value,
        "status": item.status,
        "triggered_at": item.triggered_at,
        "processed_at": item.processed_at,
        "created_at": item.triggered_at,
        "updated_at": now,
        "metadata": {"acknowledged_at": now},
    }
    return _format_incident(row)


@router.post("/{incident_id}/resolve")
async def resolve_incident(
    incident_id: str,
    request: ResolveRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Resolve an incident; optional resolution notes are accepted."""
    tenant_id = await _require_tenant(auth)
    actor = auth.user.email if auth.user else "system"
    now = _now_iso()

    if is_supabase_db_enabled():
        row = await _get_incident_row(tenant_id=tenant_id, incident_id=incident_id)
        if not row:
            raise HTTPException(status_code=404, detail="incident_not_found")

        metadata = _extract_metadata(row)
        metadata["resolved_at"] = now
        if request.resolution:
            metadata["resolution_notes"] = request.resolution

        updated = await _update_incident_row(
            tenant_id=tenant_id,
            incident_id=incident_id,
            updates={
                "status": "resolved",
                "resolved_at": now,
                "processed_at": now,
                "metadata": metadata,
            },
        )

        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        await db.create_incident_event(
            incident_id=incident_id,
            tenant_id=tenant_id,
            event_type="resolved",
            title="Incident resolved",
            description="Incident resolved",
            actor=actor,
            metadata={"actor": actor, "resolution": request.resolution},
            occurred_at=now,
        )

        asyncio.create_task(
            _capture_resolution_memory_best_effort(
                incident=updated or row,
                resolution=request.resolution,
                resolved_at=now,
            )
        )

        return _format_incident(updated or row)

    item = await incident_store.get_incident(incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="incident_not_found")

    item.status = "completed"
    item.processed_at = _as_datetime(now)

    metadata: dict[str, Any] = {"resolved_at": now}
    if request.resolution:
        metadata["resolution_notes"] = request.resolution

    _IN_MEMORY_TIMELINE.setdefault(incident_id, []).append(
        {
            "id": f"{incident_id}-resolved-{len(_IN_MEMORY_TIMELINE.get(incident_id, [])) + 1}",
            "incident_id": incident_id,
            "event_type": "resolved",
            "description": "Incident resolved",
            "actor": actor,
            "occurred_at": now,
            "metadata": {"actor": actor, "resolution": request.resolution},
        }
    )

    resolution_row = {
        "id": item.incident_id,
        "title": item.title,
        "description": None,
        "service": item.service_name,
        "service_name": item.service_name,
        "severity": item.severity.value,
        "status": item.status,
        "triggered_at": item.triggered_at,
        "processed_at": item.processed_at,
        "created_at": item.triggered_at,
        "updated_at": now,
        "resolved_at": now,
        "metadata": metadata,
    }

    asyncio.create_task(
        _capture_resolution_memory_best_effort(
            incident=resolution_row,
            resolution=request.resolution,
            resolved_at=now,
        )
    )

    row = {
        "id": item.incident_id,
        "title": item.title,
        "service": item.service_name,
        "severity": item.severity.value,
        "status": item.status,
        "triggered_at": item.triggered_at,
        "processed_at": item.processed_at,
        "created_at": item.triggered_at,
        "updated_at": now,
        "metadata": metadata,
    }
    return _format_incident(row)


@router.get("/{incident_id}/context")
async def get_incident_context(
    incident_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Get the latest context card for an incident."""
    tenant_id = await _require_tenant(auth)

    if is_supabase_db_enabled():
        row = await _get_incident_row(tenant_id=tenant_id, incident_id=incident_id)
        if not row:
            raise HTTPException(status_code=404, detail="incident_not_found")

        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        try:
            card_row = await db.get_context_card(incident_id)
        except Exception as exc:
            logger.warning(
                "incident_context_fetch_failed",
                error=str(exc),
                incident_id=incident_id,
            )
            card_row = None

        if not card_row:
            enriched_payload = await _try_ondemand_enrichment(row, tenant_id=tenant_id)
            return _map_context_payload(
                incident_id=incident_id,
                payload=enriched_payload,
                context_id="",
                created_at=row.get("created_at"),
                github_status=await _get_github_status(
                    row,
                    tenant_id=tenant_id,
                    payload=enriched_payload,
                ),
            )

        stored_payload = card_row.get("data")
        return _map_context_payload(
            incident_id=incident_id,
            payload=stored_payload,
            context_id=card_row.get("id"),
            created_at=card_row.get("created_at"),
            github_status=await _get_github_status(
                row,
                tenant_id=tenant_id,
                payload=stored_payload,
            ),
        )

    item = await incident_store.get_incident(incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="incident_not_found")

    if not item.context_card:
        enriched_payload = await _try_ondemand_enrichment(
            {
                "id": item.incident_id,
                "service": item.service_name,
                "service_name": item.service_name,
            },
            tenant_id=tenant_id,
        )
        return _map_context_payload(
            incident_id=incident_id,
            payload=enriched_payload,
            context_id="",
            created_at=item.triggered_at,
            github_status=await _get_github_status(
                {
                    "service": item.service_name,
                    "service_name": item.service_name,
                },
                tenant_id=tenant_id,
                payload=enriched_payload,
            ),
        )

    payload = item.context_card.model_dump(mode="json")
    return _map_context_payload(
        incident_id=incident_id,
        payload=payload,
        context_id=payload.get("incident_id") or "",
        created_at=payload.get("assembled_at") or item.triggered_at,
        github_status=await _get_github_status(
            {
                "service": item.service_name,
                "service_name": item.service_name,
            },
            tenant_id=tenant_id,
            payload=payload,
        ),
    )


@router.get("/{incident_id}/timeline")
async def get_incident_timeline(
    incident_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Return timeline events for an incident."""
    tenant_id = await _require_tenant(auth)

    if is_supabase_db_enabled():
        row = await _get_incident_row(tenant_id=tenant_id, incident_id=incident_id)
        if not row:
            raise HTTPException(status_code=404, detail="incident_not_found")

        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        events = await db.list_incident_events(incident_id)
        comments = await db.list_comments(incident_id)
        card_row = await db.get_context_card(incident_id)

        timeline = [_event_to_timeline(event, incident_id) for event in events]
        for comment in comments:
            timeline.append(
                {
                    "id": str(comment.get("id", "")),
                    "incident_id": incident_id,
                    "type": "comment",
                    "description": comment.get("content") or "Note added",
                    "actor": comment.get("author_name"),
                    "timestamp": _iso(comment.get("created_at")) or _now_iso(),
                    "metadata": {"note": True},
                }
            )
        timeline.extend(
            await _github_timeline_events_from_context(
                incident_id,
                incident_row=row,
                stored_context_payload=(
                    card_row.get("data") if isinstance(card_row, dict) else None
                ),
                tenant_id=tenant_id,
            )
        )

        timeline.sort(key=lambda item: item.get("timestamp") or "")
        return timeline

    item = await incident_store.get_incident(incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="incident_not_found")

    incident = {
        "created_at": _iso(item.triggered_at),
        "acknowledged_at": None,
        "resolved_at": _iso(item.processed_at) if item.status == "completed" else None,
    }

    return await _build_timeline_from_inmemory(
        incident_id,
        incident,
        incident_row={
            "id": item.incident_id,
            "service": item.service_name,
            "service_name": item.service_name,
        },
        stored_context_payload=(
            item.context_card.model_dump(mode="json") if item.context_card else None
        ),
        tenant_id=tenant_id,
    )


@router.post("/{incident_id}/notes")
async def add_incident_note(
    incident_id: str,
    request: NoteRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Add a note/comment to an incident."""
    tenant_id = await _require_tenant(auth)
    actor = auth.user.email if auth.user else "system"
    now = _now_iso()

    if is_supabase_db_enabled():
        row = await _get_incident_row(tenant_id=tenant_id, incident_id=incident_id)
        if not row:
            raise HTTPException(status_code=404, detail="incident_not_found")

        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        comment = await db.create_comment(
            incident_id=incident_id,
            tenant_id=tenant_id,
            author_name=actor,
            content=request.content,
        )

        await db.create_incident_event(
            incident_id=incident_id,
            tenant_id=tenant_id,
            event_type="comment",
            title="Note added",
            description=request.content,
            actor=actor,
            metadata={"note_id": comment.get("id")},
            occurred_at=now,
        )

        return {
            "id": comment.get("id"),
            "incident_id": incident_id,
            "content": comment.get("content") or request.content,
            "author": comment.get("author_name") or actor,
            "created_at": _iso(comment.get("created_at")) or now,
        }

    item = await incident_store.get_incident(incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="incident_not_found")

    note_id = f"note-{incident_id}-{len(_IN_MEMORY_NOTES.get(incident_id, [])) + 1}"
    payload = {
        "id": note_id,
        "incident_id": incident_id,
        "content": request.content,
        "author": actor,
        "created_at": now,
    }

    _IN_MEMORY_NOTES.setdefault(incident_id, []).append(payload)
    _IN_MEMORY_TIMELINE.setdefault(incident_id, []).append(
        {
            "id": note_id,
            "incident_id": incident_id,
            "event_type": "comment",
            "description": request.content,
            "actor": actor,
            "occurred_at": now,
            "metadata": {"note": True},
        }
    )
    return payload


@router.get("/{incident_id}/similar")
async def get_similar_incidents(
    incident_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Return a small list of incidents similar by service/severity heuristics."""
    tenant_id = await _require_tenant(auth)

    if is_supabase_db_enabled():
        current = await _get_incident_row(tenant_id=tenant_id, incident_id=incident_id)
        if not current:
            raise HTTPException(status_code=404, detail="incident_not_found")

        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)

        def _do():
            return (
                db.client.table("incidents")
                .select("*")
                .eq("tenant_id", tenant_id)
                .neq("id", incident_id)
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )

        result = await db._to_thread(_do)
        rows = list(result.data or [])

        current_service = current.get("service")
        current_severity = _normalize_severity(current.get("severity"))
        ranked = sorted(
            rows,
            key=lambda row: (
                0 if row.get("service") == current_service else 1,
                (
                    0
                    if _normalize_severity(row.get("severity")) == current_severity
                    else 1
                ),
                -(
                    int(_as_datetime(row.get("created_at")).timestamp())
                    if _as_datetime(row.get("created_at"))
                    else 0
                ),
            ),
        )

        return [_format_incident(row) for row in ranked[:5]]

    current = await incident_store.get_incident(incident_id)
    if not current:
        raise HTTPException(status_code=404, detail="incident_not_found")

    all_incidents = await incident_store.get_all_incidents()
    candidates = [item for item in all_incidents if item.incident_id != incident_id]
    candidates.sort(
        key=lambda item: (
            0 if item.service_name == current.service_name else 1,
            0 if item.severity.value == current.severity.value else 1,
            -int(item.triggered_at.timestamp()),
        )
    )

    rows = [
        {
            "id": item.incident_id,
            "title": item.title,
            "service": item.service_name,
            "severity": item.severity.value,
            "status": item.status,
            "triggered_at": item.triggered_at,
            "processed_at": item.processed_at,
            "created_at": item.triggered_at,
            "updated_at": item.processed_at or item.triggered_at,
            "metadata": {},
        }
        for item in candidates[:5]
    ]
    return [_format_incident(row) for row in rows]
