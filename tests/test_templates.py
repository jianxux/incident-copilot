"""Tests for incident templates module."""

import pytest

from src.templates.models import (
    IncidentTemplate,
    TemplateCategory,
    TemplateCreateRequest,
    TemplateField,
    FieldType,
)
from src.templates.defaults import get_builtin_templates, get_builtin_template
from src.templates.service import TemplateService


class TestTemplateModels:
    def test_template_creation(self):
        t = IncidentTemplate(
            id="db-outage",
            name="Database Outage",
            title_pattern="DB Outage - {service}",
            description="Template for database-related incidents",
            category=TemplateCategory.DATABASE,
        )
        assert t.name == "Database Outage"
        assert t.category == TemplateCategory.DATABASE

    def test_category_values(self):
        assert TemplateCategory.INFRASTRUCTURE
        assert TemplateCategory.APPLICATION
        assert TemplateCategory.DATABASE
        assert TemplateCategory.SECURITY

    def test_template_field(self):
        f = TemplateField(
            name="region",
            label="AWS Region",
            field_type=FieldType.TEXT,
        )
        assert f.name == "region"

    def test_create_request(self):
        req = TemplateCreateRequest(
            name="New Template",
            title_pattern="{service} - {severity}",
            description="A test template",
            category=TemplateCategory.CUSTOM,
        )
        assert req.name == "New Template"


class TestDefaultTemplates:
    def test_get_builtin_templates(self):
        templates = get_builtin_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_builtin_templates_have_required_fields(self):
        templates = get_builtin_templates()
        for t in templates:
            assert t.name
            assert t.id

    def test_get_builtin_template_by_id(self):
        templates = get_builtin_templates()
        first = templates[0]
        found = get_builtin_template(first.id)
        assert found is not None
        assert found.id == first.id

    def test_get_builtin_template_not_found(self):
        result = get_builtin_template("nonexistent-id")
        assert result is None


class TestTemplateService:
    @pytest.fixture
    def service(self):
        return TemplateService()

    def test_service_instantiation(self, service):
        assert service is not None

    @pytest.mark.asyncio
    async def test_get_all_templates(self, service):
        templates = await service.get_all("tenant-1")
        assert isinstance(templates, list)
        assert len(templates) > 0
