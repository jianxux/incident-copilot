"""Storage for incident templates."""

import asyncio
from datetime import datetime

import structlog

from .models import (
    IncidentTemplate,
    RenderedChecklist,
    TemplateCategory,
    TemplateCreateRequest,
    TemplateUpdateRequest,
)

logger = structlog.get_logger()


class TemplateStore:
    """In-memory store for incident templates with multi-tenant support."""

    def __init__(self):
        self._templates: dict[str, IncidentTemplate] = {}
        self._checklists: dict[str, RenderedChecklist] = {}
        self._by_incident: dict[str, list[str]] = {}  # incident_id -> [checklist_ids]
        self._lock = asyncio.Lock()

    async def save(self, template: IncidentTemplate) -> IncidentTemplate:
        """Save a template."""
        async with self._lock:
            template.updated_at = datetime.utcnow()
            self._templates[template.id] = template
            logger.info(
                "template_saved",
                template_id=template.id,
                name=template.name,
                category=template.category.value,
                tenant_id=template.tenant_id,
            )
            return template

    async def create(
        self, 
        request: TemplateCreateRequest,
        created_by: str | None = None,
    ) -> IncidentTemplate:
        """Create a new template from a request."""
        import uuid
        
        template = IncidentTemplate(
            id=f"tmpl-{uuid.uuid4().hex[:12]}",
            name=request.name,
            description=request.description,
            category=request.category,
            steps=request.steps,
            keywords=request.keywords,
            service_tags=request.service_tags,
            severity_levels=request.severity_levels,
            tags=request.tags,
            runbook_ids=request.runbook_ids,
            runbook_urls=request.runbook_urls,
            tenant_id=request.tenant_id,
            created_by=created_by,
            is_builtin=False,
        )
        return await self.save(template)

    async def get(self, template_id: str) -> IncidentTemplate | None:
        """Get a template by ID."""
        return self._templates.get(template_id)

    async def update(
        self, 
        template_id: str, 
        updates: TemplateUpdateRequest,
    ) -> IncidentTemplate | None:
        """Update an existing template."""
        async with self._lock:
            template = self._templates.get(template_id)
            if not template:
                return None
            
            update_data = updates.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if value is not None:
                    setattr(template, field, value)
            
            template.updated_at = datetime.utcnow()
            template.version += 1
            
            logger.info(
                "template_updated",
                template_id=template_id,
                version=template.version,
            )
            return template

    async def delete(self, template_id: str) -> bool:
        """Delete a template by ID."""
        async with self._lock:
            if template_id in self._templates:
                template = self._templates.pop(template_id)
                logger.info(
                    "template_deleted",
                    template_id=template_id,
                    name=template.name,
                )
                return True
            return False

    async def list(
        self,
        category: TemplateCategory | None = None,
        tenant_id: str | None = None,
        include_builtin: bool = True,
        enabled_only: bool = True,
        limit: int = 100,
    ) -> list[IncidentTemplate]:
        """List templates with optional filters."""
        templates = list(self._templates.values())
        
        # Filter by enabled status
        if enabled_only:
            templates = [t for t in templates if t.enabled]
        
        # Filter by category
        if category:
            templates = [t for t in templates if t.category == category]
        
        # Filter by tenant (include builtin if requested)
        if tenant_id:
            templates = [
                t for t in templates 
                if t.tenant_id == tenant_id or (include_builtin and t.is_builtin)
            ]
        elif not include_builtin:
            templates = [t for t in templates if not t.is_builtin]
        
        # Sort by use count (most used first), then by name
        templates.sort(key=lambda t: (-t.use_count, t.name))
        
        return templates[:limit]

    async def list_by_keywords(
        self,
        keywords: list[str],
        tenant_id: str | None = None,
        limit: int = 10,
    ) -> list[IncidentTemplate]:
        """List templates matching any of the given keywords."""
        keywords_lower = {k.lower() for k in keywords}
        templates = await self.list(tenant_id=tenant_id, limit=1000)
        
        matches = []
        for template in templates:
            template_keywords = {k.lower() for k in template.keywords}
            if template_keywords & keywords_lower:
                matches.append(template)
        
        return matches[:limit]

    async def list_by_service(
        self,
        service_name: str,
        tenant_id: str | None = None,
        limit: int = 10,
    ) -> list[IncidentTemplate]:
        """List templates matching a service name."""
        service_lower = service_name.lower()
        templates = await self.list(tenant_id=tenant_id, limit=1000)
        
        matches = []
        for template in templates:
            for tag in template.service_tags:
                if tag.lower() in service_lower or service_lower in tag.lower():
                    matches.append(template)
                    break
        
        return matches[:limit]

    async def increment_use_count(self, template_id: str) -> None:
        """Increment the use count for a template."""
        async with self._lock:
            if template_id in self._templates:
                template = self._templates[template_id]
                template.use_count += 1
                template.last_used_at = datetime.utcnow()

    async def get_builtin_templates(self) -> list[IncidentTemplate]:
        """Get all built-in templates."""
        return [t for t in self._templates.values() if t.is_builtin]

    async def get_tenant_templates(
        self, 
        tenant_id: str,
        include_builtin: bool = True,
    ) -> list[IncidentTemplate]:
        """Get templates for a specific tenant."""
        return await self.list(
            tenant_id=tenant_id, 
            include_builtin=include_builtin,
        )

    # Checklist management

    async def save_checklist(self, checklist: RenderedChecklist) -> RenderedChecklist:
        """Save a rendered checklist."""
        async with self._lock:
            checklist.updated_at = datetime.utcnow()
            self._checklists[checklist.id] = checklist
            
            # Index by incident
            if checklist.incident_id not in self._by_incident:
                self._by_incident[checklist.incident_id] = []
            if checklist.id not in self._by_incident[checklist.incident_id]:
                self._by_incident[checklist.incident_id].append(checklist.id)
            
            logger.info(
                "checklist_saved",
                checklist_id=checklist.id,
                incident_id=checklist.incident_id,
                template_id=checklist.template_id,
            )
            return checklist

    async def get_checklist(self, checklist_id: str) -> RenderedChecklist | None:
        """Get a checklist by ID."""
        return self._checklists.get(checklist_id)

    async def get_checklists_for_incident(
        self, 
        incident_id: str,
    ) -> list[RenderedChecklist]:
        """Get all checklists for an incident."""
        checklist_ids = self._by_incident.get(incident_id, [])
        return [
            self._checklists[cid] 
            for cid in checklist_ids 
            if cid in self._checklists
        ]

    async def delete_checklist(self, checklist_id: str) -> bool:
        """Delete a checklist."""
        async with self._lock:
            if checklist_id in self._checklists:
                checklist = self._checklists.pop(checklist_id)
                # Remove from incident index
                if checklist.incident_id in self._by_incident:
                    self._by_incident[checklist.incident_id] = [
                        cid for cid in self._by_incident[checklist.incident_id]
                        if cid != checklist_id
                    ]
                logger.info("checklist_deleted", checklist_id=checklist_id)
                return True
            return False

    async def clear(self):
        """Clear all templates and checklists (for testing)."""
        async with self._lock:
            self._templates.clear()
            self._checklists.clear()
            self._by_incident.clear()


# Global store instance
template_store = TemplateStore()
