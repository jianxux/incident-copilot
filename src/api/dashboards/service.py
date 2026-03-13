"""Dashboard service for CRUD, cloning, and sharing operations."""

import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

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
from .widgets import validate_widget_config


class DashboardNotFoundError(Exception):
    pass


class WidgetNotFoundError(Exception):
    pass


class PermissionDeniedError(Exception):
    pass


class DashboardService:
    def __init__(self) -> None:
        self._dashboards: dict[UUID, Dashboard] = {}
        self._public_tokens: dict[str, UUID] = {}

    async def create_dashboard(
        self, owner_id: UUID, data: DashboardCreate
    ) -> Dashboard:
        did, now = uuid4(), datetime.now(UTC)
        widgets = []
        for wd in data.widgets:
            if errs := validate_widget_config(wd.config):
                raise ValueError(f"Invalid widget: {errs}")
            widgets.append(
                Widget(
                    id=uuid4(),
                    dashboard_id=did,
                    created_at=now,
                    updated_at=now,
                    **wd.model_dump(),
                )
            )

        dashboard = Dashboard(
            id=did,
            owner_id=owner_id,
            name=data.name,
            description=data.description,
            layout=data.layout,
            tags=data.tags,
            is_default=data.is_default,
            role=data.role,
            widgets=widgets,
            created_at=now,
            updated_at=now,
        )
        self._dashboards[did] = dashboard
        return dashboard

    async def get_dashboard(self, did: UUID, user_id: UUID | None = None) -> Dashboard:
        if (d := self._dashboards.get(did)) is None:
            raise DashboardNotFoundError(f"Dashboard {did} not found")
        if user_id and not await self._can_view(d, user_id):
            raise PermissionDeniedError("No access")
        return d

    async def get_by_public_token(self, token: str) -> Dashboard:
        if (did := self._public_tokens.get(token)) is None:
            raise DashboardNotFoundError("Invalid share link")
        d = self._dashboards.get(did)
        if not d or d.share_config.scope != ShareScope.PUBLIC:
            raise DashboardNotFoundError("Not found")
        if d.share_config.expires_at and datetime.now(UTC) > d.share_config.expires_at:
            raise DashboardNotFoundError("Link expired")
        return d

    async def list_dashboards(
        self,
        user_id: UUID,
        team_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        role: str | None = None,
    ) -> list[DashboardSummary]:
        results = []
        for d in self._dashboards.values():
            if not await self._can_view(d, user_id, team_ids):
                continue
            if tags and not any(t in d.tags for t in tags):
                continue
            if role and d.role != role:
                continue
            results.append(
                DashboardSummary(
                    id=d.id,
                    name=d.name,
                    description=d.description,
                    owner_id=d.owner_id,
                    widget_count=len(d.widgets),
                    share_scope=d.share_config.scope,
                    tags=d.tags,
                    updated_at=d.updated_at,
                )
            )
        return sorted(results, key=lambda x: x.updated_at, reverse=True)

    async def update_dashboard(
        self, did: UUID, user_id: UUID, data: DashboardUpdate
    ) -> Dashboard:
        d = await self.get_dashboard(did, user_id)
        if not await self._can_edit(d, user_id):
            raise PermissionDeniedError("No edit access")
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(d, k, v)
        d.updated_at = datetime.now(UTC)
        return d

    async def delete_dashboard(self, did: UUID, user_id: UUID) -> None:
        d = await self.get_dashboard(did, user_id)
        if d.owner_id != user_id:
            raise PermissionDeniedError("Only owner can delete")
        if d.share_config.public_token:
            self._public_tokens.pop(d.share_config.public_token, None)
        del self._dashboards[did]

    async def add_widget(self, did: UUID, user_id: UUID, data: WidgetCreate) -> Widget:
        d = await self.get_dashboard(did, user_id)
        if not await self._can_edit(d, user_id):
            raise PermissionDeniedError("No edit access")
        if errs := validate_widget_config(data.config):
            raise ValueError(f"Invalid widget: {errs}")
        w = Widget(id=uuid4(), dashboard_id=did, **data.model_dump())
        d.widgets.append(w)
        d.updated_at = datetime.now(UTC)
        return w

    async def update_widget(
        self, did: UUID, wid: UUID, user_id: UUID, data: WidgetUpdate
    ) -> Widget:
        d = await self.get_dashboard(did, user_id)
        if not await self._can_edit(d, user_id):
            raise PermissionDeniedError("No edit access")
        w = next((x for x in d.widgets if x.id == wid), None)
        if not w:
            raise WidgetNotFoundError(f"Widget {wid} not found")
        if data.config and (errs := validate_widget_config(data.config)):
            raise ValueError(f"Invalid config: {errs}")
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(w, k, v)
        w.updated_at = d.updated_at = datetime.now(UTC)
        return w

    async def delete_widget(self, did: UUID, wid: UUID, user_id: UUID) -> None:
        d = await self.get_dashboard(did, user_id)
        if not await self._can_edit(d, user_id):
            raise PermissionDeniedError("No edit access")
        d.widgets = [x for x in d.widgets if x.id != wid]
        d.updated_at = datetime.now(UTC)

    async def reorder_widgets(
        self, did: UUID, user_id: UUID, positions: dict[UUID, dict[str, int]]
    ) -> Dashboard:
        d = await self.get_dashboard(did, user_id)
        if not await self._can_edit(d, user_id):
            raise PermissionDeniedError("No edit access")
        for w in d.widgets:
            if w.id in positions:
                for k, v in positions[w.id].items():
                    setattr(w.position, k, v)
        d.updated_at = datetime.now(UTC)
        return d

    async def clone_dashboard(
        self, did: UUID, user_id: UUID, new_name: str | None = None
    ) -> Dashboard:
        src = await self.get_dashboard(did, user_id)
        nid, now = uuid4(), datetime.now(UTC)
        widgets = [
            Widget(
                id=uuid4(),
                dashboard_id=nid,
                title=w.title,
                description=w.description,
                config=w.config.model_copy(deep=True),
                position=w.position.model_copy(),
                refresh_interval_seconds=w.refresh_interval_seconds,
                date_range=w.date_range.model_copy(),
                created_at=now,
                updated_at=now,
            )
            for w in src.widgets
        ]
        clone = Dashboard(
            id=nid,
            owner_id=user_id,
            name=new_name or f"{src.name} (Copy)",
            description=src.description,
            layout=src.layout.model_copy(),
            tags=src.tags.copy(),
            widgets=widgets,
            created_at=now,
            updated_at=now,
            cloned_from=src.id,
        )
        self._dashboards[nid] = clone
        return clone

    async def update_sharing(
        self,
        did: UUID,
        user_id: UUID,
        scope: ShareScope,
        team_ids: list[UUID] | None = None,
        user_ids: list[UUID] | None = None,
        allow_edit: bool = False,
        expires_at: datetime | None = None,
    ) -> ShareConfig:
        d = await self.get_dashboard(did, user_id)
        if d.owner_id != user_id:
            raise PermissionDeniedError("Only owner can share")
        token = d.share_config.public_token
        if scope == ShareScope.PUBLIC and not token:
            token = secrets.token_urlsafe(32)
            self._public_tokens[token] = did
        elif scope != ShareScope.PUBLIC and token:
            self._public_tokens.pop(token, None)
            token = None
        d.share_config = ShareConfig(
            scope=scope,
            team_ids=team_ids or [],
            shared_with_users=user_ids or [],
            public_token=token,
            expires_at=expires_at,
            allow_edit=allow_edit,
        )
        d.updated_at = datetime.now(UTC)
        return d.share_config

    async def _can_view(
        self, d: Dashboard, uid: UUID, teams: list[UUID] | None = None
    ) -> bool:
        if d.owner_id == uid:
            return True
        s = d.share_config
        if s.scope == ShareScope.PUBLIC or uid in s.shared_with_users:
            return True
        if s.scope == ShareScope.TEAM and teams and any(t in s.team_ids for t in teams):
            return True
        return s.scope == ShareScope.ORGANIZATION

    async def _can_edit(self, d: Dashboard, uid: UUID) -> bool:
        return d.owner_id == uid or (
            d.share_config.allow_edit and uid in d.share_config.shared_with_users
        )


_service: DashboardService | None = None


def get_dashboard_service() -> DashboardService:
    global _service
    if _service is None:
        _service = DashboardService()
    return _service
