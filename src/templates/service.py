"""Template service for managing incident templates."""

import uuid
from datetime import datetime
from typing import Any

from .defaults import get_builtin_templates
from .matcher import suggest_templates
from .models import (
    AppliedTemplate,
    IncidentTemplate,
    TemplateAnalytics,
    TemplateCreateRequest,
    TemplateExport,
    TemplateMatch,
    TemplateUpdateRequest,
    TemplateVersion,
)


class TemplateService:
    """Service for managing incident templates."""

    def __init__(self):
        self._templates: dict[str, IncidentTemplate] = {}
        self._org_templates: dict[str, dict[str, IncidentTemplate]] = {}
        for t in get_builtin_templates():
            self._templates[t.id] = t

    async def get_all(
        self, org_id: str | None = None, include_inactive: bool = False
    ) -> list[IncidentTemplate]:
        """Get all templates, optionally filtered by organization."""
        templates = list(self._templates.values())
        if org_id and org_id in self._org_templates:
            templates.extend(self._org_templates[org_id].values())
        if not include_inactive:
            templates = [t for t in templates if t.is_active]
        return sorted(templates, key=lambda t: (not t.is_builtin, t.name))

    async def get(self, template_id: str, org_id: str | None = None) -> IncidentTemplate | None:
        """Get a template by ID."""
        if template_id in self._templates:
            return self._templates[template_id].model_copy(deep=True)
        if org_id and org_id in self._org_templates and template_id in self._org_templates[org_id]:
            return self._org_templates[org_id][template_id].model_copy(deep=True)
        return None

    async def create(
        self, req: TemplateCreateRequest, org_id: str | None = None, created_by: str | None = None
    ) -> IncidentTemplate:
        """Create a new template."""
        now = datetime.utcnow()
        template = IncidentTemplate(
            id=f"template-{uuid.uuid4().hex[:12]}",
            name=req.name,
            description=req.description,
            category=req.category,
            title_pattern=req.title_pattern,
            severity_default=req.severity_default,
            runbook_urls=req.runbook_urls,
            initial_actions=req.initial_actions,
            stakeholders=req.stakeholders,
            fields=req.fields,
            match_patterns=req.match_patterns,
            tags=req.tags,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=created_by,
        )
        if org_id:
            self._org_templates.setdefault(org_id, {})[template.id] = template
        else:
            self._templates[template.id] = template
        return template

    async def update(
        self,
        template_id: str,
        req: TemplateUpdateRequest,
        org_id: str | None = None,
        updated_by: str | None = None,
    ) -> IncidentTemplate | None:
        """Update a template with versioning."""
        template = await self.get(template_id, org_id)
        if not template or template.is_builtin:
            return None

        # Save version
        template.version_history.append(
            TemplateVersion(
                version=template.version,
                created_at=template.updated_at,
                created_by=template.created_by,
                changes=f"Updated by {updated_by}" if updated_by else "Updated",
                template_snapshot=template.model_dump(exclude={"version_history", "analytics"}),
            )
        )

        for field, value in req.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(template, field, value)

        template.version += 1
        template.updated_at = datetime.utcnow()
        self._save(template)
        return template

    def _save(self, template: IncidentTemplate) -> None:
        if template.organization_id:
            self._org_templates.setdefault(template.organization_id, {})[template.id] = template
        else:
            self._templates[template.id] = template

    async def delete(self, template_id: str, org_id: str | None = None, hard: bool = False) -> bool:
        """Delete a template (soft by default)."""
        template = await self.get(template_id, org_id)
        if not template or template.is_builtin:
            return False

        if hard:
            if template_id in self._templates:
                del self._templates[template_id]
            elif org_id and template_id in self._org_templates.get(org_id, {}):
                del self._org_templates[org_id][template_id]
            return True

        template.is_active = False
        template.updated_at = datetime.utcnow()
        self._save(template)
        return True

    async def suggest(
        self,
        title: str,
        description: str | None = None,
        service: str | None = None,
        source: str | None = None,
        tags: list[str] | None = None,
        org_id: str | None = None,
        limit: int = 5,
    ) -> list[TemplateMatch]:
        """Suggest templates based on alert content."""
        return suggest_templates(
            await self.get_all(org_id), title, description, service, source, tags, limit
        )

    async def apply(
        self, template_id: str, field_values: dict[str, Any], org_id: str | None = None
    ) -> AppliedTemplate | None:
        """Apply a template with field values."""
        template = await self.get(template_id, org_id)
        if not template:
            return None

        title = template.title_pattern
        for k, v in field_values.items():
            title = title.replace(f"{{{k}}}", str(v))

        await self._record_usage(template_id, org_id)
        return AppliedTemplate(
            template_id=template.id,
            template_name=template.name,
            generated_title=title,
            severity=template.severity_default,
            runbook_urls=template.runbook_urls,
            initial_actions=template.initial_actions,
            stakeholders=template.stakeholders,
            custom_fields=field_values,
        )

    async def customize(
        self, template_id: str, org_id: str, created_by: str | None = None
    ) -> IncidentTemplate | None:
        """Create an org-specific copy of a template."""
        original = await self.get(template_id)
        if not original:
            return None

        now = datetime.utcnow()
        copy = original.model_copy(deep=True)
        copy.id = f"custom-{uuid.uuid4().hex[:12]}"
        copy.name = f"{original.name} (Custom)"
        copy.organization_id = org_id
        copy.is_builtin = False
        copy.version = 1
        copy.version_history = []
        copy.analytics = TemplateAnalytics()
        copy.created_at = copy.updated_at = now
        copy.created_by = created_by

        self._org_templates.setdefault(org_id, {})[copy.id] = copy
        return copy

    async def _record_usage(self, template_id: str, org_id: str | None) -> None:
        template = await self.get(template_id, org_id)
        if template:
            template.analytics.usage_count += 1
            template.analytics.last_used_at = datetime.utcnow()
            self._save(template)

    async def record_resolution(
        self,
        template_id: str,
        resolution_minutes: float,
        escalated: bool,
        org_id: str | None = None,
    ) -> None:
        """Record resolution metrics for analytics."""
        template = await self.get(template_id, org_id)
        if not template:
            return

        a = template.analytics
        count = a.usage_count or 1
        if a.avg_resolution_time_minutes is None:
            a.avg_resolution_time_minutes = resolution_minutes
        else:
            a.avg_resolution_time_minutes = (
                a.avg_resolution_time_minutes * (count - 1) + resolution_minutes
            ) / count

        success = 0.0 if escalated else 1.0
        a.success_rate = (
            success if a.success_rate is None else (a.success_rate * (count - 1) + success) / count
        )
        self._save(template)

    async def get_analytics(self, org_id: str | None = None) -> list[dict]:
        """Get analytics for all templates."""
        return [
            {
                "template_id": t.id,
                "template_name": t.name,
                "category": t.category,
                "is_builtin": t.is_builtin,
                **t.analytics.model_dump(),
            }
            for t in await self.get_all(org_id, include_inactive=True)
        ]

    async def export_templates(
        self, template_ids: list[str] | None = None, org_id: str | None = None
    ) -> TemplateExport:
        """Export templates to portable format."""
        templates = await self.get_all(org_id)
        if template_ids:
            templates = [t for t in templates if t.id in template_ids]
        else:
            templates = [t for t in templates if not t.is_builtin]
        return TemplateExport(templates=templates)

    async def import_templates(
        self, export: TemplateExport, org_id: str, created_by: str | None = None
    ) -> list[IncidentTemplate]:
        """Import templates from export format."""
        imported = []
        now = datetime.utcnow()
        for t in export.templates:
            copy = t.model_copy(deep=True)
            copy.id = f"imported-{uuid.uuid4().hex[:12]}"
            copy.organization_id = org_id
            copy.is_builtin = False
            copy.version = 1
            copy.version_history = []
            copy.analytics = TemplateAnalytics()
            copy.created_at = copy.updated_at = now
            copy.created_by = created_by
            self._org_templates.setdefault(org_id, {})[copy.id] = copy
            imported.append(copy)
        return imported


_service: TemplateService | None = None


def get_template_service() -> TemplateService:
    """Get or create the template service singleton."""
    global _service
    if _service is None:
        _service = TemplateService()
    return _service
