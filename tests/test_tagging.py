"""Tests for incident tagging system."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.tags import incidents_router
from src.api.tags import router as tags_router

from src.config import Settings
from src.tagging import (
    AutoTagRuleCreate,
    AutoTagRuleType,
    Tag,
    TagColor,
    TagCreate,
    TaggingService,
    TagStore,
    TagUpdate,
    reset_tagging_service,
)
from src.tagging.suggestions import TagSuggester


@pytest.fixture
def tag_store():
    """Create a fresh tag store for testing."""
    return TagStore()


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(anthropic_api_key="test-api-key")


@pytest.fixture
def service(tag_store, settings):
    """Create a tagging service with a clean store."""
    suggester = TagSuggester(settings)
    return TaggingService(store=tag_store, suggester=suggester, settings=settings)


@pytest.fixture
def app():
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(tags_router)
    app.include_router(incidents_router, prefix="/api/incidents")
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    reset_tagging_service()
    return TestClient(app)


@pytest.fixture
async def sample_tags(tag_store):
    """Create sample tags for testing."""
    await tag_store.initialize()
    payments = await tag_store.create_tag(
        TagCreate(name="payments", color=TagColor.BLUE)
    )
    database = await tag_store.create_tag(
        TagCreate(name="database", color=TagColor.GREEN)
    )
    critical = await tag_store.create_tag(
        TagCreate(name="critical", color=TagColor.RED)
    )
    stripe = await tag_store.create_tag(
        TagCreate(name="stripe", color=TagColor.PURPLE, parent_id=payments.id)
    )
    return {
        "payments": payments,
        "database": database,
        "critical": critical,
        "stripe": stripe,
    }


class TestTagStore:
    """Tests for TagStore."""

    @pytest.mark.asyncio
    async def test_create_tag(self, tag_store):
        """Test creating a tag."""
        await tag_store.initialize()
        tag = await tag_store.create_tag(
            TagCreate(
                name="test-tag", color=TagColor.BLUE, description="Test description"
            )
        )
        assert tag.name == "test-tag"
        assert tag.color == TagColor.BLUE
        assert tag.id.startswith("tag-")

    @pytest.mark.asyncio
    async def test_get_tag(self, tag_store):
        """Test getting a tag by ID."""
        await tag_store.initialize()
        created = await tag_store.create_tag(TagCreate(name="get-test"))
        retrieved = await tag_store.get_tag(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_get_tag_by_name(self, tag_store):
        """Test getting a tag by name."""
        await tag_store.initialize()
        await tag_store.create_tag(TagCreate(name="FindMe"))
        retrieved = await tag_store.get_tag_by_name("findme")
        assert retrieved is not None
        assert retrieved.name == "FindMe"

    @pytest.mark.asyncio
    async def test_update_tag(self, tag_store):
        """Test updating a tag."""
        await tag_store.initialize()
        tag = await tag_store.create_tag(TagCreate(name="original"))
        updated = await tag_store.update_tag(
            tag.id, TagUpdate(name="updated", color=TagColor.RED)
        )
        assert updated is not None
        assert updated.name == "updated"
        assert updated.color == TagColor.RED

    @pytest.mark.asyncio
    async def test_delete_tag(self, tag_store):
        """Test deleting a tag."""
        await tag_store.initialize()
        tag = await tag_store.create_tag(TagCreate(name="to-delete"))
        deleted = await tag_store.delete_tag(tag.id)
        assert deleted is True
        assert await tag_store.get_tag(tag.id) is None

    @pytest.mark.asyncio
    async def test_list_tags(self, tag_store, sample_tags):
        """Test listing tags."""
        tags, total = await tag_store.list_tags(include_children=True)
        assert total == 4
        assert len(tags) == 4


class TestIncidentTagAssociations:
    """Tests for incident-tag associations."""

    @pytest.mark.asyncio
    async def test_add_tags_to_incident(self, tag_store, sample_tags):
        """Test adding tags to an incident."""
        added = await tag_store.add_tags_to_incident(
            incident_id="INC-001",
            tag_ids=[sample_tags["payments"].id, sample_tags["critical"].id],
        )
        assert len(added) == 2

    @pytest.mark.asyncio
    async def test_remove_tag_from_incident(self, tag_store, sample_tags):
        """Test removing a tag from an incident."""
        await tag_store.add_tags_to_incident(
            incident_id="INC-003",
            tag_ids=[sample_tags["payments"].id],
        )
        removed = await tag_store.remove_tag_from_incident(
            "INC-003", sample_tags["payments"].id
        )
        assert removed is True
        tags = await tag_store.get_incident_tags("INC-003")
        assert len(tags) == 0

    @pytest.mark.asyncio
    async def test_get_incident_tags(self, tag_store, sample_tags):
        """Test getting all tags for an incident."""
        await tag_store.add_tags_to_incident(
            incident_id="INC-004",
            tag_ids=[sample_tags["payments"].id, sample_tags["database"].id],
        )
        tags = await tag_store.get_incident_tags("INC-004")
        assert len(tags) == 2


class TestAutoTagRules:
    """Tests for auto-tagging rules."""

    @pytest.mark.asyncio
    async def test_create_auto_rule(self, tag_store, sample_tags):
        """Test creating an auto-tag rule."""
        rule = await tag_store.create_auto_rule(
            AutoTagRuleCreate(
                tag_id=sample_tags["payments"].id,
                rule_type=AutoTagRuleType.SERVICE_NAME,
                pattern="payments-api",
            )
        )
        assert rule.id.startswith("rule-")
        assert rule.tag_id == sample_tags["payments"].id

    @pytest.mark.asyncio
    async def test_evaluate_service_name_rule(self, tag_store, sample_tags):
        """Test evaluating service name rule."""
        await tag_store.create_auto_rule(
            AutoTagRuleCreate(
                tag_id=sample_tags["payments"].id,
                rule_type=AutoTagRuleType.SERVICE_NAME,
                pattern="payments-api",
            )
        )
        matches = await tag_store.evaluate_auto_rules(
            incident_id="INC-050",
            service_name="payments-api",
            title="High error rate",
            severity="high",
        )
        assert len(matches) == 1
        assert matches[0][0] == sample_tags["payments"].id


class TestTaggingService:
    """Tests for TaggingService."""

    @pytest.mark.asyncio
    async def test_create_tag_validates_parent(self, service, tag_store):
        """Test that creating a tag validates parent exists."""
        await tag_store.initialize()
        with pytest.raises(ValueError, match="Parent tag .* not found"):
            await service.create_tag(TagCreate(name="child", parent_id="nonexistent"))

    @pytest.mark.asyncio
    async def test_create_tag_prevents_duplicates(self, service, tag_store):
        """Test that duplicate tag names are prevented."""
        await tag_store.initialize()
        await service.create_tag(TagCreate(name="unique-tag"))
        with pytest.raises(ValueError, match="already exists"):
            await service.create_tag(TagCreate(name="unique-tag"))

    @pytest.mark.asyncio
    async def test_get_tag_hierarchy(self, service, tag_store, sample_tags):
        """Test getting tag hierarchy."""
        hierarchy = await service.get_tag_hierarchy()
        assert len(hierarchy) == 3
        payments_hierarchy = next(h for h in hierarchy if h.tag.name == "payments")
        assert len(payments_hierarchy.children) == 1
        assert payments_hierarchy.children[0].tag.name == "stripe"


class TestTagSuggester:
    """Tests for TagSuggester."""

    def test_fallback_suggestions_service_match(self, settings):
        """Test fallback suggestions with service name match."""
        suggester = TagSuggester(Settings(anthropic_api_key=""))
        tags = [
            Tag(id="tag-1", name="payments", color=TagColor.BLUE),
            Tag(id="tag-2", name="database", color=TagColor.GREEN),
        ]
        suggestions = suggester._fallback_suggestions(
            service_name="payments-api",
            severity="medium",
            available_tags=tags,
            max_suggestions=5,
        )
        assert len(suggestions) >= 1
        assert suggestions[0].tag_id == "tag-1"

    @pytest.mark.asyncio
    async def test_suggest_tags_without_ai(self, settings):
        """Test suggestions without AI configured."""
        suggester = TagSuggester(Settings(anthropic_api_key=""))
        tags = [
            Tag(id="tag-1", name="payments", color=TagColor.BLUE),
            Tag(id="tag-2", name="high", color=TagColor.RED),
        ]
        suggestions = await suggester.suggest_tags(
            title="Payment processing failed",
            service_name="payments-api",
            severity="high",
            description=None,
            available_tags=tags,
        )
        assert len(suggestions) >= 1

    @pytest.mark.asyncio
    async def test_suggest_tags_with_mocked_ai(self, settings):
        """Test suggestions with mocked AI responses."""
        suggester = TagSuggester(settings)
        tags = [
            Tag(id="tag-1", name="payments", color=TagColor.BLUE),
            Tag(id="tag-2", name="database", color=TagColor.GREEN),
        ]
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "tag_id": "tag-1",
                            "tag_name": "payments",
                            "confidence": 0.95,
                            "reason": "Service is payments-api",
                        }
                    ]
                )
            )
        ]
        with patch.object(
            suggester.client.messages, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_response
            suggestions = await suggester.suggest_tags(
                title="Payment processing failed",
                service_name="payments-api",
                severity="high",
                description="Payment gateway timeout",
                available_tags=tags,
            )
            assert len(suggestions) == 1
            assert suggestions[0].tag_id == "tag-1"


class TestTagRoutes:
    """Tests for tag API routes."""

    def test_create_tag(self, client):
        """Test POST /api/tags."""
        response = client.post("/api/tags", json={"name": "test-tag", "color": "blue"})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-tag"
        assert data["color"] == "blue"

    def test_create_tag_duplicate_name(self, client):
        """Test creating tag with duplicate name fails."""
        client.post("/api/tags", json={"name": "duplicate"})
        response = client.post("/api/tags", json={"name": "duplicate"})
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_get_tag(self, client):
        """Test GET /api/tags/{id}."""
        create_response = client.post("/api/tags", json={"name": "get-test"})
        tag_id = create_response.json()["id"]
        response = client.get(f"/api/tags/{tag_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "get-test"

    def test_get_tag_not_found(self, client):
        """Test GET /api/tags/{id} with non-existent ID."""
        response = client.get("/api/tags/nonexistent")
        assert response.status_code == 404

    def test_update_tag(self, client):
        """Test PUT /api/tags/{id}."""
        create_response = client.post("/api/tags", json={"name": "update-test"})
        tag_id = create_response.json()["id"]
        response = client.put(
            f"/api/tags/{tag_id}", json={"name": "updated-name", "color": "red"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "updated-name"

    def test_delete_tag(self, client):
        """Test DELETE /api/tags/{id}."""
        create_response = client.post("/api/tags", json={"name": "delete-test"})
        tag_id = create_response.json()["id"]
        response = client.delete(f"/api/tags/{tag_id}")
        assert response.status_code == 200
        get_response = client.get(f"/api/tags/{tag_id}")
        assert get_response.status_code == 404

    def test_list_tags(self, client):
        """Test GET /api/tags."""
        client.post("/api/tags", json={"name": "list-1"})
        client.post("/api/tags", json={"name": "list-2"})
        response = client.get("/api/tags")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2


class TestIncidentTagRoutes:
    """Tests for incident tag routes."""

    def test_add_tags_to_incident(self, client):
        """Test POST /api/incidents/{id}/tags."""
        tag_response = client.post("/api/tags", json={"name": "incident-tag"})
        tag_id = tag_response.json()["id"]
        response = client.post(
            "/api/incidents/INC-001/tags", json={"tag_ids": [tag_id]}
        )
        assert response.status_code == 200
        tags = response.json()
        assert len(tags) == 1
        assert tags[0]["id"] == tag_id

    def test_get_incident_tags(self, client):
        """Test GET /api/incidents/{id}/tags."""
        tag_response = client.post("/api/tags", json={"name": "get-incident-tag"})
        tag_id = tag_response.json()["id"]
        client.post("/api/incidents/INC-002/tags", json={"tag_ids": [tag_id]})
        response = client.get("/api/incidents/INC-002/tags")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_remove_tag_from_incident(self, client):
        """Test DELETE /api/incidents/{id}/tags/{tag_id}."""
        tag_response = client.post("/api/tags", json={"name": "remove-tag"})
        tag_id = tag_response.json()["id"]
        client.post("/api/incidents/INC-003/tags", json={"tag_ids": [tag_id]})
        response = client.delete(f"/api/incidents/INC-003/tags/{tag_id}")
        assert response.status_code == 200


class TestAutoTagRuleRoutes:
    """Tests for auto-tag rule routes."""

    def test_create_auto_rule(self, client):
        """Test POST /api/tags/rules/auto."""
        tag_response = client.post("/api/tags", json={"name": "auto-tag"})
        tag_id = tag_response.json()["id"]
        response = client.post(
            "/api/tags/rules/auto",
            json={
                "tag_id": tag_id,
                "rule_type": "service_name",
                "pattern": "payments-api",
            },
        )
        assert response.status_code == 201
        assert response.json()["tag_id"] == tag_id

    def test_list_auto_rules(self, client):
        """Test GET /api/tags/rules/auto."""
        tag_response = client.post("/api/tags", json={"name": "list-rule-tag"})
        tag_id = tag_response.json()["id"]
        client.post(
            "/api/tags/rules/auto",
            json={
                "tag_id": tag_id,
                "rule_type": "service_name",
                "pattern": "test-service",
            },
        )
        response = client.get("/api/tags/rules/auto")
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_auto_tag_incident(self, client):
        """Test POST /api/incidents/{id}/tags/auto."""
        tag_response = client.post("/api/tags", json={"name": "auto-applied"})
        tag_id = tag_response.json()["id"]
        client.post(
            "/api/tags/rules/auto",
            json={
                "tag_id": tag_id,
                "rule_type": "service_name",
                "pattern": "target-service",
            },
        )
        response = client.post(
            "/api/incidents/INC-AUTO/tags/auto",
            params={
                "service_name": "target-service",
                "title": "Test incident",
                "severity": "medium",
            },
        )
        assert response.status_code == 200
        tags = response.json()
        assert len(tags) == 1
        assert tags[0]["id"] == tag_id


class TestTagSuggestionRoutes:
    """Tests for tag suggestion routes."""

    def test_suggest_tags(self, client):
        """Test POST /api/tags/suggest."""
        client.post("/api/tags", json={"name": "payments"})
        client.post("/api/tags", json={"name": "database"})
        response = client.post(
            "/api/tags/suggest",
            params={
                "title": "Payment processing failed",
                "service_name": "payments-api",
                "severity": "high",
            },
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
