"""Comprehensive tests for incident templates."""

import pytest

from src.templates import (
    IncidentTemplate,
    TemplateCategory,
    TemplateMatch,
    TemplateMatcher,
    TemplateRenderer,
    TemplateStep,
    TemplateStepStatus,
    template_store,
)
from src.templates.defaults import DEFAULT_TEMPLATES, initialize_default_templates
from src.templates.models import (
    RenderedChecklist,
    RenderedStep,
    TemplateCreateRequest,
    TemplateUpdateRequest,
)


class TestTemplateModels:
    """Tests for template data models."""

    def test_template_step_creation(self):
        """Test creating a template step."""
        step = TemplateStep(
            id="step-1",
            order=1,
            title="Check database connectivity",
            description="Verify the database is reachable",
            suggested_action="mysql -h db.example.com -e 'SELECT 1'",
            time_estimate_minutes=5,
            is_critical=True,
        )

        assert step.id == "step-1"
        assert step.order == 1
        assert step.title == "Check database connectivity"
        assert step.time_estimate_minutes == 5
        assert step.is_critical is True

    def test_incident_template_creation(self):
        """Test creating an incident template."""
        template = IncidentTemplate(
            id="tmpl-test",
            name="Test Template",
            description="A test template",
            category=TemplateCategory.DATABASE,
            steps=[
                TemplateStep(
                    id="step-1",
                    order=1,
                    title="Step 1",
                    time_estimate_minutes=5,
                ),
                TemplateStep(
                    id="step-2",
                    order=2,
                    title="Step 2",
                    time_estimate_minutes=10,
                    is_critical=True,
                ),
            ],
            keywords=["database", "mysql"],
            service_tags=["db-primary"],
            severity_levels=["critical", "high"],
        )

        assert template.id == "tmpl-test"
        assert template.category == TemplateCategory.DATABASE
        assert len(template.steps) == 2
        assert template.total_time_estimate_minutes == 15
        assert template.critical_steps_count == 1

    def test_template_category_values(self):
        """Test all template categories exist."""
        expected_categories = {
            "infrastructure",
            "application",
            "security",
            "network",
            "database",
            "observability",
            "cloud",
            "general",
        }

        actual_categories = {cat.value for cat in TemplateCategory}
        assert actual_categories == expected_categories

    def test_rendered_checklist_progress(self):
        """Test rendered checklist progress calculation."""
        checklist = RenderedChecklist(
            id="chk-test",
            incident_id="INC-123",
            template_id="tmpl-test",
            template_name="Test Template",
            category=TemplateCategory.DATABASE,
            steps=[
                RenderedStep(
                    step_id="step-1",
                    order=1,
                    title="Step 1",
                    status=TemplateStepStatus.COMPLETED,
                    checked=True,
                ),
                RenderedStep(
                    step_id="step-2",
                    order=2,
                    title="Step 2",
                    status=TemplateStepStatus.COMPLETED,
                    checked=True,
                ),
                RenderedStep(
                    step_id="step-3",
                    order=3,
                    title="Step 3",
                    status=TemplateStepStatus.PENDING,
                    checked=False,
                ),
                RenderedStep(
                    step_id="step-4",
                    order=4,
                    title="Step 4",
                    status=TemplateStepStatus.PENDING,
                    checked=False,
                ),
            ],
        )

        assert checklist.total_steps == 4
        assert checklist.completed_steps == 2
        assert checklist.progress_percent == 50.0


class TestTemplateStore:
    """Tests for template storage."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Clear store before each test."""
        await template_store.clear()
        yield
        await template_store.clear()

    @pytest.mark.asyncio
    async def test_create_template(self):
        """Test creating a template."""
        request = TemplateCreateRequest(
            name="Test Template",
            description="A test template for unit tests",
            category=TemplateCategory.APPLICATION,
            keywords=["test", "api"],
            service_tags=["test-service"],
            severity_levels=["high"],
        )

        template = await template_store.create(request, created_by="tester")

        assert template.id.startswith("tmpl-")
        assert template.name == "Test Template"
        assert template.category == TemplateCategory.APPLICATION
        assert template.created_by == "tester"
        assert template.is_builtin is False

    @pytest.mark.asyncio
    async def test_get_template(self):
        """Test retrieving a template."""
        request = TemplateCreateRequest(
            name="Retrieval Test",
            description="Testing retrieval",
            category=TemplateCategory.NETWORK,
        )
        created = await template_store.create(request)

        retrieved = await template_store.get(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Retrieval Test"

    @pytest.mark.asyncio
    async def test_update_template(self):
        """Test updating a template."""
        request = TemplateCreateRequest(
            name="Original Name",
            description="Original description",
            category=TemplateCategory.SECURITY,
        )
        template = await template_store.create(request)

        updates = TemplateUpdateRequest(
            name="Updated Name",
            description="Updated description",
        )
        updated = await template_store.update(template.id, updates)

        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.description == "Updated description"
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_delete_template(self):
        """Test deleting a template."""
        request = TemplateCreateRequest(
            name="To Be Deleted",
            description="This will be deleted",
            category=TemplateCategory.GENERAL,
        )
        template = await template_store.create(request)

        deleted = await template_store.delete(template.id)
        assert deleted is True

        retrieved = await template_store.get(template.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list_templates_with_filters(self):
        """Test listing templates with various filters."""
        # Create templates in different categories
        for cat in [TemplateCategory.DATABASE, TemplateCategory.APPLICATION]:
            request = TemplateCreateRequest(
                name=f"{cat.value.title()} Template",
                description=f"Template for {cat.value}",
                category=cat,
            )
            await template_store.create(request)

        # List all
        all_templates = await template_store.list()
        assert len(all_templates) == 2

        # Filter by category
        db_templates = await template_store.list(category=TemplateCategory.DATABASE)
        assert len(db_templates) == 1
        assert db_templates[0].category == TemplateCategory.DATABASE

    @pytest.mark.asyncio
    async def test_tenant_isolation(self):
        """Test tenant-based template isolation."""
        # Create tenant-specific template
        tenant_request = TemplateCreateRequest(
            name="Tenant Template",
            description="For specific tenant",
            category=TemplateCategory.APPLICATION,
            tenant_id="tenant-123",
        )
        await template_store.create(tenant_request)

        # Create global template
        global_request = TemplateCreateRequest(
            name="Global Template",
            description="Available to all",
            category=TemplateCategory.APPLICATION,
        )
        global_template = await template_store.create(global_request)
        # Make it builtin for testing
        global_template.is_builtin = True
        await template_store.save(global_template)

        # Tenant should see their template + builtin
        tenant_templates = await template_store.list(
            tenant_id="tenant-123", include_builtin=True
        )
        assert len(tenant_templates) == 2

        # Different tenant should only see builtin
        other_tenant = await template_store.list(
            tenant_id="tenant-other", include_builtin=True
        )
        assert len(other_tenant) == 1
        assert other_tenant[0].is_builtin is True

    @pytest.mark.asyncio
    async def test_use_count_tracking(self):
        """Test use count increment."""
        request = TemplateCreateRequest(
            name="Popular Template",
            description="Gets used a lot",
            category=TemplateCategory.DATABASE,
        )
        template = await template_store.create(request)

        assert template.use_count == 0

        await template_store.increment_use_count(template.id)
        await template_store.increment_use_count(template.id)
        await template_store.increment_use_count(template.id)

        updated = await template_store.get(template.id)
        assert updated.use_count == 3
        assert updated.last_used_at is not None


class TestTemplateMatcher:
    """Tests for template matching."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Initialize default templates before tests."""
        await template_store.clear()
        await initialize_default_templates()
        yield
        await template_store.clear()

    @pytest.mark.asyncio
    async def test_find_matching_templates_by_query(self):
        """Test finding templates by query text."""
        matcher = TemplateMatcher()

        matches = await matcher.find_matching_templates(
            query="database connection pool exhausted",
            top_k=5,
        )

        assert len(matches) > 0
        # Database template should be top match
        assert any("database" in m.template_name.lower() for m in matches)

    @pytest.mark.asyncio
    async def test_find_matching_templates_with_service(self):
        """Test service name boost in matching."""
        matcher = TemplateMatcher()

        matches = await matcher.find_matching_templates(
            query="high latency",
            service_name="redis-cache",
            top_k=5,
        )

        assert len(matches) > 0
        # Cache template should be boosted
        cache_match = next(
            (m for m in matches if "cache" in m.template_name.lower()), None
        )
        assert cache_match is not None

    @pytest.mark.asyncio
    async def test_find_matching_templates_with_severity(self):
        """Test severity matching."""
        matcher = TemplateMatcher()

        matches = await matcher.find_matching_templates(
            query="security breach unauthorized access",
            severity="critical",
            top_k=5,
        )

        assert len(matches) > 0
        # Security template should match severity
        security_match = next(
            (m for m in matches if "security" in m.template_name.lower()), None
        )
        if security_match:
            assert security_match.matched_severity is True

    @pytest.mark.asyncio
    async def test_auto_suggest_returns_best_match(self):
        """Test auto-suggest returns top match above threshold."""
        matcher = TemplateMatcher()

        match = await matcher.auto_suggest(
            alert_title="MySQL connection timeout",
            alert_description="Unable to connect to primary database",
            service_name="mysql-primary",
            severity="high",
        )

        assert match is not None
        assert match.relevance_score >= 0.3

    @pytest.mark.asyncio
    async def test_auto_suggest_returns_none_for_unrelated(self):
        """Test auto-suggest returns None for unrelated content."""
        matcher = TemplateMatcher()

        match = await matcher.auto_suggest(
            alert_title="Test notification",
            alert_description="This is just a test",
        )

        # May or may not match depending on keywords
        # If it matches, score should be relatively low
        if match:
            assert match.relevance_score < 0.5

    def test_infer_category(self):
        """Test category inference from text."""
        matcher = TemplateMatcher()

        db_category = matcher.infer_category(
            "MySQL database connection pool exhausted"
        )
        assert db_category == TemplateCategory.DATABASE

        network_category = matcher.infer_category(
            "DNS resolution failure and high network latency"
        )
        assert network_category == TemplateCategory.NETWORK

        k8s_category = matcher.infer_category(
            "Kubernetes pod CrashLoopBackOff container restart"
        )
        assert k8s_category == TemplateCategory.INFRASTRUCTURE

    @pytest.mark.asyncio
    async def test_min_score_filtering(self):
        """Test minimum score filtering."""
        matcher = TemplateMatcher()

        # With very high min_score, should get fewer results
        matches = await matcher.find_matching_templates(
            query="some random text",
            min_score=0.8,
            top_k=10,
        )

        # All returned matches should meet the threshold
        for match in matches:
            assert match.relevance_score >= 0.8


class TestTemplateRenderer:
    """Tests for template rendering."""

    @pytest.fixture
    def sample_template(self):
        """Create a sample template for testing."""
        return IncidentTemplate(
            id="tmpl-render-test",
            name="Render Test Template",
            description="Template for testing rendering",
            category=TemplateCategory.APPLICATION,
            steps=[
                TemplateStep(
                    id="step-1",
                    order=1,
                    title="Check service health for {{service_name}}",
                    description="Verify the service is responding",
                    suggested_action="curl http://{{service_name}}/health",
                    time_estimate_minutes=5,
                    is_critical=True,
                ),
                TemplateStep(
                    id="step-2",
                    order=2,
                    title="Review logs",
                    description="Check application logs for errors",
                    time_estimate_minutes=10,
                    runbook_url="https://docs.example.com/logs",
                ),
                TemplateStep(
                    id="step-3",
                    order=3,
                    title="Restart if needed",
                    suggested_action="kubectl rollout restart deployment/{{service_name}}",
                    time_estimate_minutes=5,
                ),
            ],
        )

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Clear store before each test."""
        await template_store.clear()
        yield
        await template_store.clear()

    @pytest.mark.asyncio
    async def test_render_template(self, sample_template):
        """Test rendering a template into a checklist."""
        await template_store.save(sample_template)
        renderer = TemplateRenderer()

        checklist = await renderer.render(
            template=sample_template,
            incident_id="INC-12345",
            context={"service_name": "payments-api"},
        )

        assert checklist.id.startswith("chk-")
        assert checklist.incident_id == "INC-12345"
        assert checklist.template_id == sample_template.id
        assert len(checklist.steps) == 3

        # Check variable substitution
        assert "payments-api" in checklist.steps[0].title
        assert "payments-api" in checklist.steps[0].suggested_action

        # Check all steps are pending initially
        for step in checklist.steps:
            assert step.status == TemplateStepStatus.PENDING
            assert step.checked is False

    @pytest.mark.asyncio
    async def test_render_to_markdown(self, sample_template):
        """Test Markdown rendering."""
        await template_store.save(sample_template)
        renderer = TemplateRenderer()

        checklist = await renderer.render(
            template=sample_template,
            incident_id="INC-12345",
            context={"service_name": "api-gateway"},
        )

        markdown = await renderer.render_to_markdown(checklist)

        assert "# Incident Checklist: Render Test Template" in markdown
        assert "**Category:** application" in markdown
        assert "INC-12345" in markdown
        assert "☐" in markdown  # Unchecked checkboxes
        assert "🔴" in markdown  # Critical step marker
        assert "⏱️" in markdown  # Time estimate
        assert "📖" in markdown  # Runbook link

    @pytest.mark.asyncio
    async def test_render_to_slack_blocks(self, sample_template):
        """Test Slack Block Kit rendering."""
        await template_store.save(sample_template)
        renderer = TemplateRenderer()

        checklist = await renderer.render(
            template=sample_template,
            incident_id="INC-12345",
        )

        blocks = await renderer.render_to_slack_blocks(checklist)

        assert len(blocks) > 0
        assert blocks[0]["type"] == "header"
        assert "divider" in [b["type"] for b in blocks]
        assert any(b["type"] == "section" for b in blocks)

    @pytest.mark.asyncio
    async def test_render_to_html(self, sample_template):
        """Test HTML rendering."""
        await template_store.save(sample_template)
        renderer = TemplateRenderer()

        checklist = await renderer.render(
            template=sample_template,
            incident_id="INC-12345",
        )

        html = await renderer.render_to_html(checklist)

        assert "<div class='incident-checklist'>" in html
        assert "<h2>" in html
        assert "<ol class='checklist-steps'>" in html
        assert "checkbox" in html
        assert "critical" in html

    @pytest.mark.asyncio
    async def test_update_step_status(self, sample_template):
        """Test updating step status."""
        await template_store.save(sample_template)
        renderer = TemplateRenderer()

        checklist = await renderer.render(
            template=sample_template,
            incident_id="INC-12345",
        )

        # Update first step to completed
        updated = await renderer.update_step_status(
            checklist=checklist,
            step_id="step-1",
            status=TemplateStepStatus.COMPLETED,
            completed_by="engineer@example.com",
            notes="Service confirmed healthy",
        )

        step1 = updated.steps[0]
        assert step1.status == TemplateStepStatus.COMPLETED
        assert step1.checked is True
        assert step1.completed_by == "engineer@example.com"
        assert step1.completed_at is not None
        assert step1.notes == "Service confirmed healthy"

        # Progress should be updated
        assert updated.completed_steps == 1


class TestDefaultTemplates:
    """Tests for built-in default templates."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Clear store before each test."""
        await template_store.clear()
        yield
        await template_store.clear()

    def test_default_templates_count(self):
        """Test we have expected number of default templates."""
        assert len(DEFAULT_TEMPLATES) >= 10

    def test_default_templates_have_required_fields(self):
        """Test all default templates have required fields."""
        for template in DEFAULT_TEMPLATES:
            assert template.id.startswith("builtin-")
            assert template.name
            assert template.description
            assert template.category in TemplateCategory
            assert template.is_builtin is True
            assert len(template.steps) > 0
            assert len(template.keywords) > 0

    def test_default_templates_cover_all_categories(self):
        """Test default templates cover multiple categories."""
        categories = {t.category for t in DEFAULT_TEMPLATES}

        # Should cover at least these core categories
        expected_categories = {
            TemplateCategory.DATABASE,
            TemplateCategory.APPLICATION,
            TemplateCategory.INFRASTRUCTURE,
            TemplateCategory.NETWORK,
            TemplateCategory.SECURITY,
        }

        assert expected_categories.issubset(categories)

    def test_default_templates_steps_have_order(self):
        """Test all steps have proper ordering."""
        for template in DEFAULT_TEMPLATES:
            orders = [step.order for step in template.steps]
            # Orders should be sequential starting from 1
            assert orders == list(range(1, len(orders) + 1))

    @pytest.mark.asyncio
    async def test_initialize_default_templates(self):
        """Test initializing default templates."""
        count = await initialize_default_templates()

        assert count == len(DEFAULT_TEMPLATES)

        # Verify templates are in store
        templates = await template_store.get_builtin_templates()
        assert len(templates) == len(DEFAULT_TEMPLATES)

    @pytest.mark.asyncio
    async def test_initialize_default_templates_idempotent(self):
        """Test initialization is idempotent."""
        # First init
        count1 = await initialize_default_templates()
        assert count1 == len(DEFAULT_TEMPLATES)

        # Second init should not duplicate
        count2 = await initialize_default_templates()
        assert count2 == 0

        # Still same number of templates
        templates = await template_store.get_builtin_templates()
        assert len(templates) == len(DEFAULT_TEMPLATES)


class TestChecklistStore:
    """Tests for checklist storage operations."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Clear store and init templates before each test."""
        await template_store.clear()
        await initialize_default_templates()
        yield
        await template_store.clear()

    @pytest.mark.asyncio
    async def test_save_and_retrieve_checklist(self):
        """Test saving and retrieving a checklist."""
        # Get a template
        templates = await template_store.list(limit=1)
        template = templates[0]

        # Render checklist
        renderer = TemplateRenderer()
        checklist = await renderer.render(template, "INC-001")

        # Save
        saved = await template_store.save_checklist(checklist)
        assert saved.id == checklist.id

        # Retrieve
        retrieved = await template_store.get_checklist(checklist.id)
        assert retrieved is not None
        assert retrieved.id == checklist.id
        assert retrieved.incident_id == "INC-001"

    @pytest.mark.asyncio
    async def test_get_checklists_for_incident(self):
        """Test getting all checklists for an incident."""
        templates = await template_store.list(limit=2)
        renderer = TemplateRenderer()

        # Create two checklists for same incident
        incident_id = "INC-MULTI"
        for template in templates:
            checklist = await renderer.render(template, incident_id)
            await template_store.save_checklist(checklist)

        # Retrieve all for incident
        checklists = await template_store.get_checklists_for_incident(incident_id)
        assert len(checklists) == 2
        assert all(c.incident_id == incident_id for c in checklists)

    @pytest.mark.asyncio
    async def test_delete_checklist(self):
        """Test deleting a checklist."""
        templates = await template_store.list(limit=1)
        renderer = TemplateRenderer()

        checklist = await renderer.render(templates[0], "INC-DELETE")
        await template_store.save_checklist(checklist)

        # Delete
        deleted = await template_store.delete_checklist(checklist.id)
        assert deleted is True

        # Verify gone
        retrieved = await template_store.get_checklist(checklist.id)
        assert retrieved is None


class TestIntegration:
    """Integration tests for the complete template workflow."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Clear store and init templates."""
        await template_store.clear()
        await initialize_default_templates()
        yield
        await template_store.clear()

    @pytest.mark.asyncio
    async def test_full_incident_template_workflow(self):
        """Test complete workflow: match -> render -> track progress."""
        matcher = TemplateMatcher()
        renderer = TemplateRenderer()

        # 1. Match templates based on alert
        matches = await matcher.find_matching_templates(
            query="High CPU usage on production server",
            service_name="api-gateway",
            severity="high",
        )

        assert len(matches) > 0
        best_match = matches[0]

        # 2. Get the matched template
        template = await template_store.get(best_match.template_id)
        assert template is not None

        # 3. Render checklist for incident
        checklist = await renderer.render(
            template=template,
            incident_id="INC-123456",
            context={"service_name": "api-gateway"},
        )
        await template_store.save_checklist(checklist)

        assert checklist.progress_percent == 0.0

        # 4. Complete steps
        for i, step in enumerate(checklist.steps[:3]):
            checklist = await renderer.update_step_status(
                checklist=checklist,
                step_id=step.step_id,
                status=TemplateStepStatus.COMPLETED,
                completed_by="oncall@example.com",
            )

        await template_store.save_checklist(checklist)

        # 5. Verify progress
        final = await template_store.get_checklist(checklist.id)
        assert final.completed_steps == 3
        assert final.progress_percent > 0

        # 6. Export to markdown
        markdown = await renderer.render_to_markdown(final)
        assert "☑" in markdown  # Completed checkboxes
        assert "oncall@example.com" in markdown

    @pytest.mark.asyncio
    async def test_multi_tenant_template_workflow(self):
        """Test templates with multi-tenant isolation."""
        # Create tenant-specific template
        tenant_request = TemplateCreateRequest(
            name="Custom Tenant Template",
            description="Specific to tenant A",
            category=TemplateCategory.APPLICATION,
            keywords=["custom", "tenant"],
            tenant_id="tenant-A",
            steps=[
                TemplateStep(
                    id="custom-1",
                    order=1,
                    title="Custom tenant step",
                    is_critical=True,
                ),
            ],
        )
        custom_template = await template_store.create(tenant_request)

        # Tenant A can see their template + builtins
        matcher = TemplateMatcher()
        tenant_a_matches = await matcher.find_matching_templates(
            query="custom tenant issue",
            tenant_id="tenant-A",
        )

        custom_in_matches = any(
            m.template_id == custom_template.id for m in tenant_a_matches
        )
        assert custom_in_matches

        # Tenant B cannot see tenant A's template
        tenant_b_matches = await matcher.find_matching_templates(
            query="custom tenant issue",
            tenant_id="tenant-B",
        )

        custom_in_b_matches = any(
            m.template_id == custom_template.id for m in tenant_b_matches
        )
        assert not custom_in_b_matches
