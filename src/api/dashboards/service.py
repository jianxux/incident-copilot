"""Dashboard service for CRUD, cloning, and sharing operations."""

import secrets
from datetime import datetime
from typing import Any
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
    """Dashboard not found."""
    pass


class WidgetNotFoundError(Exception):
    """Widget not found."""
    pass


class PermissionDeniedError(Exception):
    """User lacks permission for this operation."""
    pass


class DashboardService:
    """Service for dashboard operations."""
    
    def __init__(self) -> None:
        # In-memory storage for demo; replace with database
        self._dashboards: dict[UUID, Dashboard] = {}
        self._public_tokens: dict[str, UUID] = {}
    
    # --- Dashboard CRUD ---
    
    async def create_dashboard(
        self, owner_id: UUID, data: DashboardCreate
    ) -> Dashboard:
        """Create a new dashboard."""
        dashboard_id = uuid4()
        now = datetime.utcnow()
        
        widgets = []
        for widget_data in data.widgets:
            errors = validate_widget_config(widget_data.config)
            if errors:
                raise ValueError(f"Invalid widget config: {errors}")
            
            widget = Widget(
                id=uuid4(),
                dashboard_id=dashboard_id,
                title=widget_data.title,
                description=widget_data.description,
                config=widget_data.config,
                position=widget_data.position,
                refresh_interval_seconds=widget_data.refresh_interval_seconds,
                date_range=widget_data.date_range,
                created_at=now,
                updated_at=now,
            )
            widgets.append(widget)
        
        dashboard = Dashboard(
            id=dashboard_id,
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
        
        self._dashboards[dashboard_id] = dashboard
        return dashboard
    
    async def get_dashboard(
        self, dashboard_id: UUID, user_id: UUID | None = None
    ) -> Dashboard:
        """Get a dashboard by ID."""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            raise DashboardNotFoundError(f"Dashboard {dashboard_id} not found")
        
        if user_id and not await self._can_view(dashboard, user_id):
            raise PermissionDeniedError("No access to this dashboard")
        
        return dashboard
    
    async def get_by_public_token(self, token: str) -> Dashboard:
        """Get a dashboard by public share token."""
        dashboard_id = self._public_tokens.get(token)
        if not dashboard_id:
            raise DashboardNotFoundError("Invalid or expired share link")
        
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard or dashboard.share_config.scope != ShareScope.PUBLIC:
            raise DashboardNotFoundError("Dashboard not found or no longer public")
        
        if dashboard.share_config.expires_at:
            if datetime.utcnow() > dashboard.share_config.expires_at:
                raise DashboardNotFoundError("Share link has expired")
        
        return dashboard
    
    async def list_dashboards(
        self,
        user_id: UUID,
        team_ids: list[UUID] | None = None,
        org_id: UUID | None = None,
        tags: list[str] | None = None,
        role: str | None = None,
    ) -> list[DashboardSummary]:
        """List dashboards accessible to a user."""
        results = []
        for dashboard in self._dashboards.values():
            if not await self._can_view(dashboard, user_id, team_ids, org_id):
                continue
            
            if tags and not any(t in dashboard.tags for t in tags):
                continue
            if role and dashboard.role != role:
                continue
            
            results.append(DashboardSummary(
                id=dashboard.id,
                name=dashboard.name,
                description=dashboard.description,
                owner_id=dashboard.owner_id,
                widget_count=len(dashboard.widgets),
                share_scope=dashboard.share_config.scope,
                tags=dashboard.tags,
                is_default=dashboard.is_default,
                role=dashboard.role,
                updated_at=dashboard.updated_at,
            ))
        
        return sorted(results, key=lambda d: d.updated_at, reverse=True)
    
    async def update_dashboard(
        self, dashboard_id: UUID, user_id: UUID, data: DashboardUpdate
    ) -> Dashboard:
        """Update dashboard metadata."""
        dashboard = await self.get_dashboard(dashboard_id, user_id)
        
        if not await self._can_edit(dashboard, user_id):
            raise PermissionDeniedError("No edit access to this dashboard")
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(dashboard, field, value)
        
        dashboard.updated_at = datetime.utcnow()
        return dashboard
    
    async def delete_dashboard(self, dashboard_id: UUID, user_id: UUID) -> None:
        """Delete a dashboard."""
        dashboard = await self.get_dashboard(dashboard_id, user_id)
        
        if dashboard.owner_id != user_id:
            raise PermissionDeniedError("Only the owner can delete a dashboard")
        
        # Clean up public token if exists
        if dashboard.share_config.public_token:
            self._public_tokens.pop(dashboard.share_config.public_token, None)
        
        del self._dashboards[dashboard_id]
    
    # --- Widget CRUD ---
    
    async def add_widget(
        self, dashboard_id: UUID, user_id: UUID, data: WidgetCreate
    ) -> Widget:
        """Add a widget to a dashboard."""
        dashboard = await self.get_dashboard(dashboard_id, user_id)
        
        if not await self._can_edit(dashboard, user_id):
            raise PermissionDeniedError("No edit access to this dashboard")
        
        errors = validate_widget_config(data.config)
        if errors:
            raise ValueError(f"Invalid widget config: {errors}")
        
        widget = Widget(
            id=uuid4(),
            dashboard_id=dashboard_id,
            title=data.title,
            description=data.description,
            config=data.config,
            position=data.position,
            refresh_interval_seconds=data.refresh_interval_seconds,
            date_range=data.date_range,
        )
        
        dashboard.widgets.append(widget)
        dashboard.updated_at = datetime.utcnow()
        return widget
    
    async def update_widget(
        self,
        dashboard_id: UUID,
        widget_id: UUID,
        user_id: UUID,
        data: WidgetUpdate,
    ) -> Widget:
        """Update a widget."""
        dashboard = await self.get_dashboard(dashboard_id, user_id)
        
        if not await self._can_edit(dashboard, user_id):
            raise PermissionDeniedError("No edit access to this dashboard")
        
        widget = next((w for w in dashboard.widgets if w.id == widget_id), None)
        if not widget:
            raise WidgetNotFoundError(f"Widget {widget_id} not found")
        
        if data.config:
            errors = validate_widget_config(data.config)
            if errors:
                raise ValueError(f"Invalid widget config: {errors}")
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(widget, field, value)
        
        widget.updated_at = datetime.utcnow()
        dashboard.updated_at = datetime.utcnow()
        return widget
    
    async def delete_widget(
        self, dashboard_id: UUID, widget_id: UUID, user_id: UUID
    ) -> None:
        """Delete a widget from a dashboard."""
        dashboard = await self.get_dashboard(dashboard_id, user_id)
        
        if not await self._can_edit(dashboard, user_id):
            raise PermissionDeniedError("No edit access to this dashboard")
        
        dashboard.widgets = [w for w in dashboard.widgets if w.id != widget_id]
        dashboard.updated_at = datetime.utcnow()
    
    async def reorder_widgets(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        positions: dict[UUID, dict[str, int]],
    ) -> Dashboard:
        """Update widget positions (for drag-and-drop)."""
        dashboard = await self.get_dashboard(dashboard_id, user_id)
        
        if not await self._can_edit(dashboard, user_id):
            raise PermissionDeniedError("No edit access to this dashboard")
        
        for widget in dashboard.widgets:
            if widget.id in positions:
                pos = positions[widget.id]
                widget.position.x = pos.get("x", widget.position.x)
                widget.position.y = pos.get("y", widget.position.y)
                widget.position.w = pos.get("w", widget.position.w)
                widget.position.h = pos.get("h", widget.position.h)
                widget.updated_at = datetime.utcnow()
        
        dashboard.updated_at = datetime.utcnow()
        return dashboard
    
    # --- Cloning ---
    
    async def clone_dashboard(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        new_name: str | None = None,
    ) -> Dashboard:
        """Clone a dashboard."""
        source = await self.get_dashboard(dashboard_id, user_id)
        
        new_id = uuid4()
        now = datetime.utcnow()
        
        cloned_widgets = []
        for widget in source.widgets:
            cloned_widgets.append(Widget(
                id=uuid4(),
                dashboard_id=new_id,
                title=widget.title,
                description=widget.description,
                config=widget.config.model_copy(deep=True),
                position=widget.position.model_copy(),
                refresh_interval_seconds=widget.refresh_interval_seconds,
                date_range=widget.date_range.model_copy(),
                created_at=now,
                updated_at=now,
            ))
        
        cloned = Dashboard(
            id=new_id,
            owner_id=user_id,
            name=new_name or f"{source.name} (Copy)",
            description=source.description,
            layout=source.layout.model_copy(),
            tags=source.tags.copy(),
            is_default=False,  # Clones are never default
            role=None,
            widgets=cloned_widgets,
            share_config=ShareConfig(),  # Reset sharing
            created_at=now,
            updated_at=now,
            cloned_from=source.id,
        )
        
        self._dashboards[new_id] = cloned
        return cloned
    
    # --- Sharing ---
    
    async def update_sharing(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        scope: ShareScope,
        team_ids: list[UUID] | None = None,
        user_ids: list[UUID] | None = None,
        allow_edit: bool = False,
        expires_at: datetime | None = None,
    ) -> ShareConfig:
        """Update dashboard sharing settings."""
        dashboard = await self.get_dashboard(dashboard_id, user_id)
        
        if dashboard.owner_id != user_id:
            raise PermissionDeniedError("Only owner can change sharing settings")
        
        # Generate public token if needed
        public_token = dashboard.share_config.public_token
        if scope == ShareScope.PUBLIC and not public_token:
            public_token = secrets.token_urlsafe(32)
            self._public_tokens[public_token] = dashboard_id
        elif scope != ShareScope.PUBLIC and public_token:
            self._public_tokens.pop(public_token, None)
            public_token = None
        
        dashboard.share_config = ShareConfig(
            scope=scope,
            team_ids=team_ids or [],
            shared_with_users=user_ids or [],
            public_token=public_token,
            expires_at=expires_at,
            allow_edit=allow_edit,
        )
        dashboard.updated_at = datetime.utcnow()
        
        return dashboard.share_config
    
    # --- Permission helpers ---
    
    async def _can_view(
        self,
        dashboard: Dashboard,
        user_id: UUID,
        team_ids: list[UUID] | None = None,
        org_id: UUID | None = None,
    ) -> bool:
        """Check if user can view dashboard."""
        if dashboard.owner_id == user_id:
            return True
        
        share = dashboard.share_config
        if share.scope == ShareScope.PUBLIC:
            return True
        if user_id in share.shared_with_users:
            return True
        if share.scope == ShareScope.TEAM and team_ids:
            if any(t in share.team_ids for t in team_ids):
                return True
        if share.scope == ShareScope.ORGANIZATION and org_id:
            return True  # Simplified; real impl checks org membership
        
        return False
    
    async def _can_edit(self, dashboard: Dashboard, user_id: UUID) -> bool:
        """Check if user can edit dashboard."""
        if dashboard.owner_id == user_id:
            return True
        if dashboard.share_config.allow_edit:
            if user_id in dashboard.share_config.shared_with_users:
                return True
        return False


# Singleton service instance
_service: DashboardService | None = None


def get_dashboard_service() -> DashboardService:
    """Get or create the dashboard service instance."""
    global _service
    if _service is None:
        _service = DashboardService()
    return _service
