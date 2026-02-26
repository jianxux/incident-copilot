"""Tests for statuspage module."""

import pytest

from src.statuspage.models import (
    Component,
    ComponentStatus,
    StatusPageIncident,
    IncidentImpact,
    IncidentStatus,
    StatusPageConfig,
    StatusPageProvider,
    StatusPageCredentials,
    SEVERITY_TO_IMPACT,
)
from src.statuspage.service import StatusPageService


class TestStatusPageModels:
    def test_component_status_values(self):
        assert ComponentStatus.OPERATIONAL
        assert ComponentStatus.DEGRADED
        assert ComponentStatus.MAJOR_OUTAGE

    def test_incident_impact_values(self):
        assert IncidentImpact.NONE
        assert IncidentImpact.MINOR
        assert IncidentImpact.MAJOR
        assert IncidentImpact.CRITICAL

    def test_component_creation(self):
        c = Component(
            id="comp-1",
            name="API",
            status=ComponentStatus.OPERATIONAL,
        )
        assert c.name == "API"

    def test_incident_creation(self):
        i = StatusPageIncident(
            name="API Degradation",
            message="Investigating API latency issues",
            impact=IncidentImpact.MINOR,
            status=IncidentStatus.INVESTIGATING,
        )
        assert i.impact == IncidentImpact.MINOR

    def test_provider_values(self):
        assert StatusPageProvider.ATLASSIAN
        assert StatusPageProvider.CACHET

    def test_severity_to_impact_mapping(self):
        assert isinstance(SEVERITY_TO_IMPACT, dict)
        assert len(SEVERITY_TO_IMPACT) > 0

    def test_config_creation(self):
        c = StatusPageConfig(
            id="cfg-1",
            name="Main Status Page",
            provider=StatusPageProvider.ATLASSIAN,
            credentials=StatusPageCredentials(api_key="test-key", page_id="page-1"),
        )
        assert c.provider == StatusPageProvider.ATLASSIAN


class TestStatusPageService:
    @pytest.fixture
    def service(self):
        return StatusPageService()

    def test_service_instantiation(self, service):
        assert service is not None
