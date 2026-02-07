"""Tests for cost calculations and tracking module."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.costs.models import (
    CostCategory,
    CostEntry,
    CostReport,
    CostTrend,
    Currency,
    EngineerRate,
    IncidentCost,
    ROIAnalysis,
    ServiceCriticality,
    ServiceRevenueConfig,
    SLAConfig,
    TeamCostAllocation,
)
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_cost_entry() -> CostEntry:
    """Create a sample cost entry."""
    return CostEntry(
        id="entry-1",
        incident_id="inc-123",
        category=CostCategory.ENGINEER_TIME,
        amount=Decimal("500.00"),
        currency=Currency.USD,
        description="4 hours of incident response",
        team="platform",
        hours_spent=4.0,
        hourly_rate=Decimal("125.00"),
    )


@pytest.fixture
def sample_incident_cost() -> IncidentCost:
    """Create a sample incident cost."""
    return IncidentCost(
        incident_id="inc-123",
        incident_title="Database outage",
        service_name="payments-api",
        severity="P1",
        started_at=datetime.utcnow() - timedelta(hours=4),
        resolved_at=datetime.utcnow(),
        total_cost=Decimal("15000.00"),
        totals_by_category={
            CostCategory.ENGINEER_TIME: Decimal("2000.00"),
            CostCategory.LOST_REVENUE: Decimal("10000.00"),
            CostCategory.SLA_PENALTY: Decimal("3000.00"),
        },
    )


class TestCurrency:
    """Tests for Currency enum."""

    def test_currency_values(self):
        """Test all currency values exist."""
        assert Currency.USD.value == "USD"
        assert Currency.EUR.value == "EUR"
        assert Currency.GBP.value == "GBP"
        assert Currency.JPY.value == "JPY"


class TestCostCategory:
    """Tests for CostCategory enum."""

    def test_category_values(self):
        """Test all cost categories exist."""
        assert CostCategory.ENGINEER_TIME.value == "engineer_time"
        assert CostCategory.LOST_REVENUE.value == "lost_revenue"
        assert CostCategory.CLOUD_RESOURCES.value == "cloud_resources"
        assert CostCategory.SLA_PENALTY.value == "sla_penalty"


class TestCostEntry:
    """Tests for CostEntry model."""

    def test_entry_creation(self, sample_cost_entry):
        """Test creating a cost entry."""
        assert sample_cost_entry.incident_id == "inc-123"
        assert sample_cost_entry.category == CostCategory.ENGINEER_TIME
        assert sample_cost_entry.amount == Decimal("500.00")

    def test_amount_usd_conversion(self):
        """Test USD amount conversion."""
        # EUR entry
        entry = CostEntry(
            id="entry-eur",
            incident_id="inc-123",
            category=CostCategory.ENGINEER_TIME,
            amount=Decimal("100.00"),
            currency=Currency.EUR,
        )
        # EUR rate is ~1.08
        assert entry.amount_usd > Decimal("100.00")
        assert entry.amount_usd == Decimal("108.00")

    def test_engineer_time_tracking(self, sample_cost_entry):
        """Test engineer time tracking fields."""
        assert sample_cost_entry.hours_spent == 4.0
        assert sample_cost_entry.hourly_rate == Decimal("125.00")

    def test_minimum_amount(self):
        """Test minimum amount validation."""
        entry = CostEntry(
            id="entry-zero",
            incident_id="inc-123",
            category=CostCategory.REMEDIATION,
            amount=Decimal("0.00"),
        )
        assert entry.amount == Decimal("0.00")


class TestEngineerRate:
    """Tests for EngineerRate model."""

    def test_rate_creation(self):
        """Test creating an engineer rate."""
        rate = EngineerRate(
            id="rate-1",
            name="Senior Engineer",
            hourly_rate=Decimal("150.00"),
            team="platform",
            level="senior",
        )
        assert rate.hourly_rate == Decimal("150.00")
        assert rate.level == "senior"

    def test_default_rate(self):
        """Test creating a default rate."""
        rate = EngineerRate(
            id="rate-default",
            name="Default Rate",
            hourly_rate=Decimal("100.00"),
            is_default=True,
        )
        assert rate.is_default


class TestServiceRevenueConfig:
    """Tests for ServiceRevenueConfig model."""

    def test_config_creation(self):
        """Test creating a service revenue config."""
        config = ServiceRevenueConfig(
            service_name="payments-api",
            criticality=ServiceCriticality.CRITICAL,
            hourly_revenue_impact=Decimal("5000.00"),
            monthly_revenue=Decimal("500000.00"),
            customer_count=10000,
        )
        assert config.criticality == ServiceCriticality.CRITICAL
        assert config.hourly_revenue_impact == Decimal("5000.00")


class TestSLAConfig:
    """Tests for SLAConfig model."""

    def test_sla_config_creation(self):
        """Test creating an SLA config."""
        config = SLAConfig(
            id="sla-1",
            customer_id="cust-123",
            customer_name="Acme Corp",
            service_level="gold",
            uptime_target=99.99,
            monthly_fee=Decimal("10000.00"),
            penalty_per_violation_pct=Decimal("2.0"),
        )
        assert config.uptime_target == 99.99
        assert config.penalty_per_violation_pct == Decimal("2.0")


class TestIncidentCost:
    """Tests for IncidentCost model."""

    def test_incident_cost_creation(self, sample_incident_cost):
        """Test creating an incident cost."""
        assert sample_incident_cost.total_cost == Decimal("15000.00")
        assert len(sample_incident_cost.totals_by_category) == 3

    def test_duration_hours(self, sample_incident_cost):
        """Test duration calculation."""
        duration = sample_incident_cost.duration_hours
        assert duration is not None
        assert duration == pytest.approx(4.0, rel=0.1)

    def test_cost_per_hour(self, sample_incident_cost):
        """Test cost per hour calculation."""
        cph = sample_incident_cost.cost_per_hour
        assert cph is not None
        # $15000 / 4 hours = $3750/hour
        assert cph == pytest.approx(Decimal("3750.00"), rel=0.1)

    def test_add_entry(self):
        """Test adding a cost entry."""
        cost = IncidentCost(
            incident_id="inc-456",
            service_name="api",
        )
        entry = CostEntry(
            id="e1",
            incident_id="inc-456",
            category=CostCategory.ENGINEER_TIME,
            amount=Decimal("500.00"),
        )
        cost.add_entry(entry)

        assert len(cost.entries) == 1
        assert cost.total_cost == Decimal("500.00")
        assert cost.totals_by_category[CostCategory.ENGINEER_TIME] == Decimal("500.00")


class TestCostTrend:
    """Tests for CostTrend model."""

    def test_trend_creation(self):
        """Test creating a cost trend."""
        trend = CostTrend(
            period="7d",
            start_date=datetime.utcnow() - timedelta(days=7),
            end_date=datetime.utcnow(),
            total_cost=Decimal("50000.00"),
            incident_count=10,
            average_cost_per_incident=Decimal("5000.00"),
            previous_total=Decimal("60000.00"),
            change_pct=-16.7,
            trend="improving",
        )
        assert trend.trend == "improving"
        assert trend.change_pct < 0  # Costs reduced


class TestCostReport:
    """Tests for CostReport model."""

    def test_report_creation(self, sample_incident_cost):
        """Test creating a cost report."""
        report = CostReport(
            report_id="report-1",
            title="Weekly Cost Report",
            period="7d",
            start_date=datetime.utcnow() - timedelta(days=7),
            end_date=datetime.utcnow(),
            total_cost=Decimal("100000.00"),
            incident_count=20,
            avg_cost_per_incident=Decimal("5000.00"),
            by_severity={"P1": Decimal("60000.00"), "P2": Decimal("40000.00")},
            top_incidents=[sample_incident_cost],
        )
        assert report.total_cost == Decimal("100000.00")
        assert len(report.top_incidents) == 1


class TestROIAnalysis:
    """Tests for ROIAnalysis model."""

    def test_positive_roi(self):
        """Test ROI analysis with positive ROI."""
        analysis = ROIAnalysis(
            analysis_id="roi-1",
            title="Prevention Investment Analysis",
            period="90d",
            start_date=datetime.utcnow() - timedelta(days=90),
            end_date=datetime.utcnow(),
            total_incident_cost=Decimal("100000.00"),
            incident_count=25,
            prevention_investment=Decimal("20000.00"),
            projected_incidents_prevented=10,
            projected_savings=Decimal("40000.00"),
            roi_pct=100.0,  # 100% ROI
            net_benefit=Decimal("20000.00"),
        )
        assert analysis.is_positive_roi
        assert analysis.roi_pct == 100.0

    def test_negative_roi(self):
        """Test ROI analysis with negative ROI."""
        analysis = ROIAnalysis(
            analysis_id="roi-2",
            title="Failed Investment",
            period="30d",
            start_date=datetime.utcnow() - timedelta(days=30),
            end_date=datetime.utcnow(),
            total_incident_cost=Decimal("10000.00"),
            incident_count=5,
            prevention_investment=Decimal("50000.00"),
            projected_incidents_prevented=2,
            projected_savings=Decimal("4000.00"),
            roi_pct=-92.0,
            net_benefit=Decimal("-46000.00"),
        )
        assert not analysis.is_positive_roi


class TestTeamCostAllocation:
    """Tests for TeamCostAllocation model."""

    def test_allocation_creation(self):
        """Test creating a team cost allocation."""
        allocation = TeamCostAllocation(
            team="platform",
            department="engineering",
            period="30d",
            start_date=datetime.utcnow() - timedelta(days=30),
            end_date=datetime.utcnow(),
            direct_costs=Decimal("15000.00"),
            support_costs=Decimal("5000.00"),
            total_costs=Decimal("20000.00"),
            by_category={
                CostCategory.ENGINEER_TIME: Decimal("12000.00"),
                CostCategory.CLOUD_RESOURCES: Decimal("8000.00"),
            },
        )
        assert allocation.total_costs == Decimal("20000.00")


class TestCostsAPI:
    """Tests for Costs API endpoints."""

    def test_get_incident_costs(self, client):
        """Test GET /api/costs/incidents/{id} endpoint."""
        response = client.get("/api/costs/incidents/inc-123")
        assert response.status_code in (200, 404)

    def test_add_cost_entry(self, client):
        """Test POST /api/costs/incidents/{id}/entries endpoint."""
        response = client.post(
            "/api/costs/incidents/inc-123/entries",
            json={
                "category": "engineer_time",
                "amount": "500.00",
                "description": "4 hours response time",
                "hours_spent": 4.0,
            },
        )
        assert response.status_code in (200, 201)

    def test_get_cost_report(self, client):
        """Test GET /api/costs/reports endpoint."""
        response = client.get("/api/costs/reports?days=30")
        assert response.status_code == 200

    def test_get_cost_trends(self, client):
        """Test GET /api/costs/trends endpoint."""
        response = client.get("/api/costs/trends?period=90d")
        assert response.status_code == 200

    def test_get_team_allocations(self, client):
        """Test GET /api/costs/allocations endpoint."""
        response = client.get("/api/costs/allocations")
        assert response.status_code == 200

    def test_configure_engineer_rates(self, client):
        """Test POST /api/costs/rates endpoint."""
        response = client.post(
            "/api/costs/rates",
            json={
                "id": "rate-1",
                "name": "Senior Engineer",
                "hourly_rate": "150.00",
                "level": "senior",
            },
        )
        assert response.status_code in (200, 201)

    def test_configure_service_revenue(self, client):
        """Test POST /api/costs/services endpoint."""
        response = client.post(
            "/api/costs/services",
            json={
                "service_name": "payments-api",
                "criticality": "critical",
                "hourly_revenue_impact": "5000.00",
            },
        )
        assert response.status_code in (200, 201)

    def test_calculate_incident_cost(self, client):
        """Test POST /api/costs/calculate endpoint."""
        response = client.post(
            "/api/costs/calculate",
            json={
                "incident_id": "inc-123",
                "include_revenue_loss": True,
            },
        )
        assert response.status_code in (200, 202)

    def test_get_roi_analysis(self, client):
        """Test GET /api/costs/roi endpoint."""
        response = client.get("/api/costs/roi?period=90d")
        assert response.status_code == 200
