"""FastAPI routes for dashboard management."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel

from .defaults import get_all_default_roles, get_default_dashboard
from .models import (
    Dashboard,
    DashboardCreate,
    DashboardSummary,
    DashboardUpdate,
    ShareConfig,
    ShareScope,
    Widget,
    WidgetCreate,
    WidgetUpdate,
)
from .service import (
    DashboardNotFoundError,
    DashboardService,
    PermissionDeniedError,
    WidgetNotFoundError,
    get_dashboard_service,
)
from .widgets import fetch_widget_data

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def get_service() -> DashboardService:
    return get_dashboard_service()


async def get_user_id() -> UUID:
    return UUID("00000000-0000-0000-0000-000000000001")  # Replace with real auth


class ShareRequest(BaseModel):
    scope: ShareScope
    team_ids: list[UUID] | None = None
    user_ids: list[UUID] | None = None
    allow_edit: bool = False
    expires_at: datetime | None = None


class WidgetPositions(BaseModel):
    positions: dict[UUID, dict[str, int]]


class CloneRequest(BaseModel):
    new_name: str | None = None


def _err(e: Exception, code: int = 404) -> None:
    raise HTTPException(status_code=code, detail=str(e))


@router.post("", response_model=Dashboard, status_code=201)
async def create_dashboard(
    data: DashboardCreate,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> Dashboard:
    try:
        return await svc.create_dashboard(uid, data)
    except ValueError as e:
        _err(e, 400)


@router.get("", response_model=list[DashboardSummary])
async def list_dashboards(
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
    tags: Annotated[list[str] | None, Query()] = None,
    role: str | None = None,
) -> list[DashboardSummary]:
    return await svc.list_dashboards(uid, tags=tags, role=role)


@router.get("/defaults/roles")
async def list_default_roles() -> list[str]:
    return get_all_default_roles()


@router.post("/defaults/{role}", response_model=Dashboard, status_code=201)
async def create_from_default(
    role: str,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> Dashboard:
    if not (t := get_default_dashboard(role)):
        _err(Exception(f"No default for role: {role}"))
    return await svc.create_dashboard(uid, t)


@router.get("/public/{token}", response_model=Dashboard)
async def get_public_dashboard(
    token: str, svc: Annotated[DashboardService, Depends(get_service)]
) -> Dashboard:
    try:
        return await svc.get_by_public_token(token)
    except DashboardNotFoundError as e:
        _err(e)


@router.get("/{did}", response_model=Dashboard)
async def get_dashboard(
    did: UUID,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> Dashboard:
    try:
        return await svc.get_dashboard(did, uid)
    except DashboardNotFoundError as e:
        _err(e)
    except PermissionDeniedError as e:
        _err(e, 403)


@router.patch("/{did}", response_model=Dashboard)
async def update_dashboard(
    did: UUID,
    data: DashboardUpdate,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> Dashboard:
    try:
        return await svc.update_dashboard(did, uid, data)
    except DashboardNotFoundError as e:
        _err(e)
    except PermissionDeniedError as e:
        _err(e, 403)


@router.delete("/{did}", status_code=204)
async def delete_dashboard(
    did: UUID,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> None:
    try:
        await svc.delete_dashboard(did, uid)
    except DashboardNotFoundError as e:
        _err(e)
    except PermissionDeniedError as e:
        _err(e, 403)


@router.post("/{did}/clone", response_model=Dashboard, status_code=201)
async def clone_dashboard(
    did: UUID,
    req: CloneRequest,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> Dashboard:
    try:
        return await svc.clone_dashboard(did, uid, req.new_name)
    except DashboardNotFoundError as e:
        _err(e)
    except PermissionDeniedError as e:
        _err(e, 403)


@router.put("/{did}/share", response_model=ShareConfig)
async def update_sharing(
    did: UUID,
    req: ShareRequest,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> ShareConfig:
    try:
        return await svc.update_sharing(
            did,
            uid,
            req.scope,
            req.team_ids,
            req.user_ids,
            req.allow_edit,
            req.expires_at,
        )
    except DashboardNotFoundError as e:
        _err(e)
    except PermissionDeniedError as e:
        _err(e, 403)


@router.post("/{did}/widgets", response_model=Widget, status_code=201)
async def add_widget(
    did: UUID,
    data: WidgetCreate,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> Widget:
    try:
        return await svc.add_widget(did, uid, data)
    except DashboardNotFoundError as e:
        _err(e)
    except PermissionDeniedError as e:
        _err(e, 403)
    except ValueError as e:
        _err(e, 400)


@router.patch("/{did}/widgets/{wid}", response_model=Widget)
async def update_widget(
    did: UUID,
    wid: UUID,
    data: WidgetUpdate,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> Widget:
    try:
        return await svc.update_widget(did, wid, uid, data)
    except (DashboardNotFoundError, WidgetNotFoundError) as e:
        _err(e)
    except PermissionDeniedError as e:
        _err(e, 403)
    except ValueError as e:
        _err(e, 400)


@router.delete("/{did}/widgets/{wid}", status_code=204)
async def delete_widget(
    did: UUID,
    wid: UUID,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> None:
    try:
        await svc.delete_widget(did, wid, uid)
    except (DashboardNotFoundError, WidgetNotFoundError) as e:
        _err(e)
    except PermissionDeniedError as e:
        _err(e, 403)


@router.put("/{did}/widgets/positions", response_model=Dashboard)
async def reorder_widgets(
    did: UUID,
    data: WidgetPositions,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> Dashboard:
    try:
        return await svc.reorder_widgets(did, uid, data.positions)
    except DashboardNotFoundError as e:
        _err(e)
    except PermissionDeniedError as e:
        _err(e, 403)


@router.get("/{did}/widgets/{wid}/data")
async def get_widget_data(
    did: UUID,
    wid: UUID,
    uid: Annotated[UUID, Depends(get_user_id)],
    svc: Annotated[DashboardService, Depends(get_service)],
) -> dict[str, Any]:
    try:
        d = await svc.get_dashboard(did, uid)
        if not (w := next((x for x in d.widgets if x.id == wid), None)):
            raise WidgetNotFoundError(f"Widget {wid} not found")
        return await fetch_widget_data(w)
    except (DashboardNotFoundError, WidgetNotFoundError) as e:
        _err(e)
    except PermissionDeniedError as e:
        _err(e, 403)


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[UUID, list[WebSocket]] = {}

    async def connect(self, did: UUID, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.setdefault(did, []).append(ws)

    def disconnect(self, did: UUID, ws: WebSocket) -> None:
        if did in self.connections:
            self.connections[did].remove(ws)


manager = ConnectionManager()


@router.websocket("/{did}/ws")
async def dashboard_ws(
    ws: WebSocket, did: UUID, svc: Annotated[DashboardService, Depends(get_service)]
) -> None:
    try:
        d = await svc.get_dashboard(did)
    except DashboardNotFoundError:
        await ws.close(code=4004)
        return

    await manager.connect(did, ws)
    try:
        for w in d.widgets:
            await ws.send_json(
                {"type": "widget_data", "payload": await fetch_widget_data(w)}
            )
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "refresh_widget":
                if w := next(
                    (x for x in d.widgets if str(x.id) == msg.get("widget_id")), None
                ):
                    await ws.send_json(
                        {
                            "type": "widget_data",
                            "payload": await fetch_widget_data(w),
                        }
                    )
            elif msg.get("type") == "refresh_all":
                for w in d.widgets:
                    await ws.send_json(
                        {
                            "type": "widget_data",
                            "payload": await fetch_widget_data(w),
                        }
                    )
            elif msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(did, ws)
