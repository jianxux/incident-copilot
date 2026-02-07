"""Tests for demo mode functionality."""

import pytest
from fastapi.testclient import TestClient

from src.demo import DEMO_SCENARIOS, DemoGenerator
from src.demo.scenarios import get_scenario, list_scenarios
from src.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestDemoScenarios:
    """Tests for demo scenario definitions."""

    def test_list_scenarios(self):
        """Test that scenarios can be listed."""
        scenarios = list_scenarios()
        assert len(scenarios) >= 3
        for scenario in scenarios:
            assert "id" in scenario
            assert "name" in scenario
            assert "description" in scenario
            assert "severity" in scenario

    def test_get_scenario(self):
        """Test getting a specific scenario."""
        scenario = get_scenario("demo-stripe-timeout")
        assert scenario is not None
        assert scenario["name"] == "Payment Processing Timeout"
        assert "alert" in scenario
        assert "deployments" in scenario
        assert "logs" in scenario
        assert "ai_summary" in scenario

    def test_get_invalid_scenario(self):
        """Test getting a non-existent scenario."""
        scenario = get_scenario("invalid-scenario-id")
        assert scenario is None

    def test_all_scenarios_have_required_fields(self):
        """Test that all scenarios have required fields."""
        required_fields = [
            "id",
            "name",
            "description",
            "alert",
            "deployments",
            "logs",
            "ai_summary",
        ]
        alert_fields = ["id", "title", "service", "severity"]

        for scenario in DEMO_SCENARIOS:
            for field in required_fields:
                assert (
                    field in scenario
                ), f"Missing field '{field}' in scenario {scenario.get('id')}"

            for field in alert_fields:
                assert (
                    field in scenario["alert"]
                ), f"Missing alert field '{field}' in scenario {scenario.get('id')}"


class TestDemoGenerator:
    """Tests for the demo generator."""

    @pytest.mark.asyncio
    async def test_generate_context_card(self):
        """Test generating a context card."""
        generator = DemoGenerator(simulate_delays=False)
        card = await generator.generate_context_card("demo-stripe-timeout")

        assert card is not None
        assert card.incident_id.startswith("demo-")
        assert card.service_name == "payments-api"
        assert card.github is not None
        assert card.datadog is not None
        assert card.ai_summary is not None
        assert len(card.github.recent_deploys) > 0

    @pytest.mark.asyncio
    async def test_generate_random_context_card(self):
        """Test generating a random context card."""
        generator = DemoGenerator(simulate_delays=False)
        card = await generator.generate_context_card()

        assert card is not None
        assert card.incident_id.startswith("demo-")
        assert card.service_name is not None

    @pytest.mark.asyncio
    async def test_stream_context_assembly(self):
        """Test streaming context assembly."""
        generator = DemoGenerator(simulate_delays=False)
        updates = []

        async for update in generator.stream_context_assembly("demo-stripe-timeout"):
            updates.append(update)

        assert len(updates) > 0
        assert updates[0]["step"] == "alert_received"
        assert updates[-1]["step"] == "complete"
        assert "context_card" in updates[-1]["data"]


class TestDemoAPI:
    """Tests for demo API endpoints."""

    def test_list_scenarios_endpoint(self, client):
        """Test the scenarios listing endpoint."""
        response = client.get("/demo/scenarios")
        assert response.status_code == 200
        data = response.json()
        assert "scenarios" in data
        assert "count" in data
        assert data["count"] >= 3

    def test_get_scenario_endpoint(self, client):
        """Test getting a specific scenario."""
        response = client.get("/demo/scenarios/demo-stripe-timeout")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Payment Processing Timeout"

    def test_trigger_demo(self, client):
        """Test triggering a demo incident."""
        response = client.post(
            "/demo/trigger?scenario_id=demo-stripe-timeout&simulate_delays=false"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["demo_mode"] is True
        assert "context_card" in data

    def test_trigger_random_demo(self, client):
        """Test triggering a random demo incident."""
        response = client.post("/demo/trigger?simulate_delays=false")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_demo_page(self, client):
        """Test the demo page loads."""
        response = client.get("/dashboard/demo")
        assert response.status_code == 200
        assert b"Demo Mode" in response.content


class TestDemoContextCard:
    """Tests for demo context card content."""

    @pytest.mark.asyncio
    async def test_stripe_scenario_content(self):
        """Test the Stripe timeout scenario has correct content."""
        generator = DemoGenerator(simulate_delays=False)
        card = await generator.generate_context_card("demo-stripe-timeout")

        # Check alert info
        assert "payments-api" in card.service_name
        assert "HIGH" in card.severity.value.upper() or "high" in card.severity.value

        # Check deployments
        assert len(card.github.recent_deploys) >= 1
        deploy = card.github.recent_deploys[0]
        assert "sarah" in deploy.author.lower() or len(deploy.author) > 0

        # Check AI summary mentions Stripe
        assert "stripe" in card.ai_summary.explanation.lower()

    @pytest.mark.asyncio
    async def test_database_scenario_content(self):
        """Test the database scenario has correct content."""
        generator = DemoGenerator(simulate_delays=False)
        card = await generator.generate_context_card("demo-database-connection")

        # Check critical severity
        assert card.severity.value == "critical"

        # Check service
        assert "user-service" in card.service_name

        # Check AI summary mentions database
        assert (
            "database" in card.ai_summary.explanation.lower()
            or "pool" in card.ai_summary.explanation.lower()
        )

    @pytest.mark.asyncio
    async def test_similar_incidents_included(self):
        """Test that similar incidents are included when available."""
        generator = DemoGenerator(simulate_delays=False)
        card = await generator.generate_context_card("demo-stripe-timeout")

        # Stripe scenario should have similar incidents
        assert len(card.similar_incidents) > 0
        assert card.similar_incidents[0].similarity_score > 0.5

    @pytest.mark.asyncio
    async def test_runbooks_included(self):
        """Test that runbooks are linked when available."""
        generator = DemoGenerator(simulate_delays=False)
        card = await generator.generate_context_card("demo-stripe-timeout")

        # Should have runbooks linked
        assert len(card.runbooks) > 0
        assert card.runbooks[0].relevance_score > 0.5
