"""Template service for managing incident templates."""

import json
import uuid
from datetime import datetime
from typing import Any

from .defaults import get_builtin_templates, get_builtin_template
from .matcher import suggest_templates, AlertData, TemplateMatcher
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
        """Initialize with in-memory storage (swap for DB in production)."""
        self._templates: dict[str, IncidentTemplate] = {}
        self._org_templates: dict[str, dict[str, IncidentTemplate]] = {}
        self._load_builtins()

    def _load_builtins(self) -> None:
        """Load built-in templates."""
        for template in get_builtin_templates():
            self._templates[template.id] = template

    async def get_all(self, organization_id: str | None = None, include_inactive: bool = False) -> list[IncidentTemplate]:
        """Get all templates, optionally filtered by organization."""
        templates = list(self._templates.values())
        
        # Add org-specific templates
        if organization_id and organization_id in self._org_templates:
            templates.extend(self._org_templates[organization_id].values())
        
        if not include_inactive:
            templates = [t for t in templates if t.is_active]
        
        return sorted(templates, key=lambda t: (not t.is_builtin, t.name))

    async def get(self, template_id: str, organization_id: str | None = None) -> IncidentTemplate | None:
        """Get a template by ID."""
        # Check global templates first
        if template_id in self._templates:
            return self._templates[template_id].model_copy(deep=True)
        
        # Check org templates
        if organization_id and organization_id in self._org_templates:
            if template_id in self._org_templates[organization_id]:
                return self._org_templates[organization_id][template_id].model_copy(deep=True)
        
        return None

    async def create(self, request: TemplateCreateRequest, organization_id: str | None = None, created_by: str | None = None) -> IncidentTemplate:
        """Create a new template."""
        template_id = f"template-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        
        template = IncidentTemplate(
            id=template_id,
            name=request.name,
            description=request.description,
            category=request.category,
            title_pattern=request.title_pattern,
            severity_default=request.severity_default,
            runbook_urls=request.runbook_urls,
            initial_actions=request.initial_actions,
            stakeholders=request.stakeholders,
            fields=request.fields,
            match_patterns=request.match_patterns,
            tags=request.tags,
            organization_id=organization_id,
            is_builtin=False,
            created_at=now,
            updated_at=now,
            created_by=created_by,
        )
        
        if organization_id:
            if organization_id not in self._org_templates:
                self._org_templates[organization_id] = {}
            self._org_templates[organization_id][template_id] = template
        else:
            self._templates[template_id] = template
        
        return template

    async def update(self, template_id: str, request: TemplateUpdateRequest, organization_id: str | None = None, updated_by: str | None = None) -> IncidentTemplate | None:
        """Update a template with versioning."""
        template = await self.get(template_id, organization_id)
        if not template or template.is_builtin:
            return None  # Can't update built-in templates
        
        # Create version snapshot
        version_snapshot = template.model_dump(exclude={"version_history", "analytics"})
        version = TemplateVersion(
            version=template.version,
            created_at=template.updated_at,
            created_by=template.created_by,
            changes=f"Updated by {updated_by}" if updated_by else "Updated",
            template_snapshot=version_snapshot,
        )
        
        # Apply updates
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(template, field, value)
        
        template.version += 1
        template.updated_at = datetime.utcnow()
        template.version_history.append(version)
        
        # Save back
        if template.organization_id:
            self._org_templates[template.organization_id][template_id] = template
        else:
            self._templates[template_id] = template
        
        return template

    async def delete(self, template_id: str, organization_id: str | None = None) -> bool:
        """Delete a template (soft delete by deactivating)."""
        template = await self.get(template_id, organization_id)
        if not template or template.is_builtin:
            return False
        
        template.is_active = False
        template.updated_at = datetime.utcnow()
        
        if template.organization_id:
            self._org_templates[template.organization_id][template_id] = template
        else:
            self._templates[template_id] = template
        
        return True

    async def hard_delete(self, template_id: str, organization_id: str | None = None) -> bool:
        """Permanently delete a template."""
        if template_id in self._templates and not self._templates[template_id].is_builtin:
            del self._templates[template_id]
            return True
        
        if organization_id and organization_id in self._org_templates:
            if template_id in self._org_templates[organization_id]:
                del self._org_templates[organization_id][template_id]
                return True
        
        return False

    async def suggest(
        self,
        title: str,
        description: str | None = None,
        service: str | None = None,
        source: str | None = None,
        tags: list[str] | None = None,
        organization_id: str | None = None,
        limit: int = 5,
    ) -> list[TemplateMatch]:
        """Suggest templates based on alert content."""
        templates = await self.get_all(organization_id)
        return suggest_templates(
            templates=templates,
            title=title,
            description=description,
            service=service,
            source=source,
            tags=tags,
            limit=limit,
        )

    async def apply(
        self,
        template_id: str,
        field_values: dict[str, Any],
        organization_id: str | None = None,
    ) -> AppliedTemplate | None:
        """Apply a template with field values to generate incident data."""
        template = await self.get(template_id, organization_id)
        if not template:
            return None
        
        # Generate title from pattern
        generated_title = template.title_pattern
        for key, value in field_values.items():
            generated_title = generated_title.replace(f"{{{key}}}", str(value))
        
        # Update analytics
        await self._record_usage(template_id, organization_id)
        
        return AppliedTemplate(
            template_id=template.id,
            template_name=template.name,
            generated_title=generated_title,
            severity=template.severity_default,
            runbook_urls=template.runbook_urls,
            initial_actions=template.initial_actions,
            stakeholders=template.stakeholders,
            custom_fields=field_values,
        )

    async def customize(self, template_id: str, organization_id: str, created_by: str | None = None) -> IncidentTemplate | None:
        """Create an org-specific copy of a template for customization."""
        original = await self.get(template_id)
        if not original:
            return None
        
        # Create a copy with new ID
        new_id = f"custom-{uuid.uuid4().hex[:12]}"
        customized = original.model_copy(deep=True)
        customized.id = new_id
        customized.name = f"{original.name} (Custom)"
        customized.organization_id = organization_id
        customized.is_builtin = False
        customized.version = 1
        customized.version_history = []
        customized.analytics = TemplateAnalytics()
        customized.created_at = datetime.utcnow()
        customized.updated_at = datetime.utcnow()
        customized.created_by = created_by
        
        if organization_id not in self._org_templates:
            self._org_templates[organization_id] = {}
        self._org_templates[organization_id][new_id] = customized
        
        return customized

    async def _record_usage(self, template_id: str, organization_id: str | None) -> None:
        """Record template usage for analytics."""
        template = await self.get(template_id, organization_id)
        if template:
            template.analytics.usage_count += 1
            template.analytics.last_used_at = datetime.utcnow()
            
            if template.organization_id:
                self._org_templates[template.organization_id][template_id] = template
            elif template_id in self._templates:
                self._templates[template_id] = template

    async def record_resolution(self, template_id: str, resolution_minutes: float, escalated: bool, organization_id: str | None = None) -> None:
        """Record resolution metrics for a template."""
        template = await self.get(template_id, organization_id)
        if not template:
            return
        
        analytics = template.analytics
        
        # Update average resolution time
        if analytics.avg_resolution_time_minutes is None:
            analytics.avg_resolution_time_minutes = resolution_minutes
        else:
            # Running average
            count = analytics.usage_count or 1
            analytics.avg_resolution_time_minutes = (
                (analytics.avg_resolution_time_minutes * (count - 1) + resolution_minutes) / count
            )
        
        # Update success rate
        if analytics.success_rate is None:
            analytics.success_rate = 0.0 if escalated else 1.0
        else:
            count = analytics.usage_count or 1
            success_delta = 0.0 if escalated else 1.0
            analytics.success_rate = (
                (analytics.success_rate * (count - 1) + success_delta) / count
            )
        
        if template.organization_id:
            self._org_templates[template.organization_id][template_id] = template
        elif template_id in self._templates:
            self._templates[template_id] = template

    async def get_analytics(self, organization_id: str | None = None) -> list[dict]:
        """Get analytics for all templates."""
        templates = await self.get_all(organization_id, include_inactive=True)
        return [
            {
                "template_id": t.id,
                "template_name": t.name,
                "category": t.category,
                "is_builtin": t.is_builtin,
                **t.analytics.model_dump(),
            }
            for t in templates
        ]

    async def export_templates(self, template_ids: list[str] | None = None, organization_id: str | None = None) -> TemplateExport:
        """Export templates to portable format."""
        all_templates = await self.get_all(organization_id)
        
        if template_ids:
            templates = [t for t in all_templates if t.id in template_ids]
        else:
            templates = [t for t in all_templates if not t.is_builtin]
        
        return TemplateExport(templates=templates)

    async def import_templates(self, export_data: TemplateExport, organization_id: str, created_by: str | None = None) -> list[IncidentTemplate]:
        """Import templates from export format."""
        imported: list[IncidentTemplate] = []
        
        for template in export_data.templates:
            # Create new IDs to avoid conflicts
            new_id = f"imported-{uuid.uuid4().hex[:12]}"
            imported_template = template.model_copy(deep=True)
            imported_template.id = new_id
            imported_template.organization_id = organization_id
            imported_template.is_builtin = False
            imported_template.version = 1
            imported_template.version_history = []
            imported_template.analytics = TemplateAnalytics()
            imported_template.created_at = datetime.utcnow()
            imported_template.updated_at = datetime.utcnow()
            imported_template.created_by = created_by
            
            if organization_id not in self._org_templates:
                self._org_templates[organization_id] = {}
            self._org_templates[organization_id][new_id] = imported_template
            imported.append(imported_template)
        
        return imported


# Singleton instance
_service: TemplateService | None = None


def get_template_service() -> TemplateService:
    """Get or create the template service singleton."""
    global _service
    if _service is None:
        _service = TemplateService()
    return _service
