"""Tests for Incident Cost Tracking module."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.costs import (
    CostBreakdown,
    CostCalculator,
    CostCategory,
    CostFactor,
    CostFactorConfig,
    CostReport,
    CostReportGenerator,
    DefaultCostFactors,
    IncidentCost,
    ReportPeriod,
    ResponderCost,
    ROIAnalysis,
    SLAPenalty,
    TeamCostSummary,
)
from src.costs.factors import HourlyRates, RevenueFactors, SLAFactors, get_cost_config
from src.costs.models import CalculateCostRequest, GenerateReportRequest
from src.costs.reports import cost_store
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def clean_store():
    """Clean the cost store before each test."""
    await cost_store.clear()
    yield cost_store
    await cost_store.clear()


@pytest.fixture
def sample_cost_request():
    """Sample cost calculation request."""
    return CalculateCostRequest(
        incident_id="INC-001",
        service_name="payments-api",
        severity="high",
        incident_started_at=datetime.utcnow() - timedelta(hours=2),
        incident_resolved_at=datetime.utcnow(),
        responders=[
            {
                "id": "U001",
                "name": "Alice",
                "team": "platform",
                "role": "sre",
                "time_minutes": 120,
            },
            {
                "id": "U002",
                "name": "Bob",
                "team": "payments",
                "role": "senior_engineer",
                "time_minutes": 90,
            },
        ],
        affected_users=5000,
        affected_transactions=250,
    )


@pytest.fixture
def sample_incident_cost():
    """Sample incident cost record."""
    now = datetime.utcnow()
    return IncidentCost(
        cost_id="COST-001",
        incident_id="INC-001",
        service_name="payments-api",
        severity="high",
        incident_started_at=now - timedelta(hours=2),
        incident_resolved_at=now,
        duration_minutes=120,
        affected_users=5000,
        affected_transactions=250,
        responder_costs=[
            ResponderCost(
                responder_id="U001",
                responder_name="Alice",
                team="platform",
                role="sre",
                hourly_rate=Decimal("175"),
                time_spent_minutes=120,
                total_cost=Decimal("350.00"),
            ),
        ],
        cost_breakdown=[
            CostBreakdown(
                category=CostCategory.REVENUE_IMPACT,
                amount=Decimal("1000.00"),
                description="Revenue impact from 120min outage",
            ),
        ],
        total_engineer_cost=Decimal("350.00"),
        total_revenue_impact=Decimal("1000.00"),
        total_cost=Decimal("1350.00"),
    )


class TestCostModels:
    """Tests for cost data models."""

    def test_incident_cost_creation(self):
        """Test creating an IncidentCost model."""
        cost = IncidentCost(
            incident_id="INC-001",
            service_name="api-gateway",
            severity="critical",
            incident_started_at=datetime.utcnow(),
        )
        assert cost.incident_id == "INC-001"
        assert cost.service_name == "api-gateway"
        assert cost.severity == "critical"
        assert cost.total_cost == Decimal("0")

    def test_incident_cost_calculate_totals(self):
        """Test calculating totals from breakdown."""
        cost = IncidentCost(
            incident_id="INC-001",
            service_name="payments-api",
            severity="high",
            incident_started_at=datetime.utcnow(),
            responder_costs=[
                ResponderCost(
                    responder_id="U001",
                    responder_name="Alice",
                    total_cost=Decimal("500.00"),
                ),
            ],
            cost_breakdown=[
                CostBreakdown(
                    category=CostCategory.REVENUE_IMPACT,
                    amount=Decimal("1000.00"),
                ),
                CostBreakdown(
                    category=CostCategory.INFRASTRUCTURE,
                    amount=Decimal("200.00"),
                ),
            ],
            sla_penalties=[
                SLAPenalty(
                    sla_id="SLA-001",
                    sla_name="Uptime SLA",
                    breach_type="uptime",
                    target_value="99.9%",
                    actual_value="99.5%",
                    penalty_amount=Decimal("500.00"),
                ),
            ],
        )

        cost.calculate_totals()

        assert cost.total_engineer_cost == Decimal("500.00")
        assert cost.total_revenue_impact == Decimal("1000.00")
        assert cost.total_sla_penalties == Decimal("500.00")
        assert cost.total_other_costs == Decimal("200.00")
        assert cost.total_cost == Decimal("2200.00")

    def test_sla_penalty_waived(self):
        """Test that waived SLA penalties are excluded from totals."""
        cost = IncidentCost(
            incident_id="INC-001",
            service_name="api",
            severity="medium",
            incident_started_at=datetime.utcnow(),
            sla_penalties=[
                SLAPenalty(
                    sla_id="SLA-001",
                    sla_name="Uptime SLA",
                    breach_type="uptime",
                    target_value="99.9%",
                    actual_value="99.5%",
                    penalty_amount=Decimal("1000.00"),
                    is_waived=True,
                    waiver_reason="Customer approved downtime",
                ),
            ],
        )

        cost.calculate_totals()
        assert cost.total_sla_penalties == Decimal("0")

    def test_cost_factor_creation(self):
        """Test creating a CostFactor."""
        factor = CostFactor(
            factor_id="test-factor",
            name="Test Factor",
            category=CostCategory.ENGINEER_TIME,
            value=Decimal("150"),
            unit="per_hour",
            applies_to=["*"],
        )
        assert factor.factor_id == "test-factor"
        assert factor.value == Decimal("150")
        assert factor.is_active is True

    def test_team_cost_summary(self):
        """Test TeamCostSummary model."""
        summary = TeamCostSummary(
            team_name="platform",
            incident_count=10,
            total_response_time_minutes=600,
            total_cost=Decimal("5000.00"),
            average_cost_per_incident=Decimal("500.00"),
            responder_count=5,
        )
        assert summary.team_name == "platform"
        assert summary.incident_count == 10


class TestHourlyRates:
    """Tests for hourly rate calculations."""

    def test_default_rate(self):
        """Test getting default hourly rate."""
        rates = HourlyRates()
        rate = rates.get_rate()
        assert rate == Decimal("150.00")

    def test_role_specific_rate(self):
        """Test getting rate for specific role."""
        rates = HourlyRates()
        sre_rate = rates.get_rate(role="sre")
        assert sre_rate == Decimal("175.00")

        senior_rate = rates.get_rate(role="senior_engineer")
        assert senior_rate == Decimal("185.00")

    def test_team_multiplier(self):
        """Test team-specific rate multipliers."""
        rates = HourlyRates()
        # Platform team has 1.1x multiplier
        rate = rates.get_rate(role="sre", team="platform")
        expected = Decimal("175.00") * Decimal("1.1")
        assert rate == expected.quantize(Decimal("0.01"))

    def test_overtime_multiplier(self):
        """Test overtime rate multiplier."""
        rates = HourlyRates()
        rate = rates.get_rate(role="sre", is_overtime=True)
        expected = Decimal("175.00") * Decimal("1.5")
        assert rate == expected.quantize(Decimal("0.01"))

    def test_weekend_multiplier(self):
        """Test weekend rate multiplier."""
        rates = HourlyRates()
        rate = rates.get_rate(role="sre", is_weekend=True)
        expected = Decimal("175.00") * Decimal("2.0")
        assert rate == expected.quantize(Decimal("0.01"))

    def test_holiday_takes_precedence(self):
        """Test that holiday multiplier takes precedence."""
        rates = HourlyRates()
        rate = rates.get_rate(role="sre", is_overtime=True, is_weekend=True, is_holiday=True)
        expected = Decimal("175.00") * Decimal("2.5")
        assert rate == expected.quantize(Decimal("0.01"))


class TestRevenueFactors:
    """Tests for revenue impact calculations."""

    def test_service_revenue_impact(self):
        """Test revenue impact calculation for known service."""
        factors = RevenueFactors()
        impact = factors.get_revenue_impact(
            service_name="payments-api",
            duration_minutes=60,
            severity="critical",
        )
        # payments-api has $500/min rate
        assert impact >= Decimal("30000.00")  # 60 * 500 * 1.0

    def test_severity_reduces_impact(self):
        """Test that lower severity reduces revenue impact."""
        factors = RevenueFactors()

        critical_impact = factors.get_revenue_impact(
            service_name="payments-api",
            duration_minutes=60,
            severity="critical",
        )

        medium_impact = factors.get_revenue_impact(
            service_name="payments-api",
            duration_minutes=60,
            severity="medium",
        )

        assert critical_impact > medium_impact

    def test_affected_users_adds_to_impact(self):
        """Test that affected users increase impact."""
        factors = RevenueFactors()

        base_impact = factors.get_revenue_impact(
            service_name="api-gateway",
            duration_minutes=60,
            severity="high",
            affected_users=0,
        )

        user_impact = factors.get_revenue_impact(
            service_name="api-gateway",
            duration_minutes=60,
            severity="high",
            affected_users=10000,
        )

        assert user_impact > base_impact

    def test_transaction_impact(self):
        """Test that affected transactions add to impact."""
        factors = RevenueFactors()

        base_impact = factors.get_revenue_impact(
            service_name="checkout-service",
            duration_minutes=30,
            severity="high",
            affected_transactions=0,
        )

        tx_impact = factors.get_revenue_impact(
            service_name="checkout-service",
            duration_minutes=30,
            severity="high",
            affected_transactions=100,
        )

        assert tx_impact > base_impact
        # 100 transactions * $50 avg = $5000 additional
        assert tx_impact >= base_impact + Decimal("3750")  # 5000 * 0.75 severity


class TestSLAFactors:
    """Tests for SLA penalty calculations."""

    def test_uptime_penalty_no_breach(self):
        """Test no penalty when SLA is met."""
        factors = SLAFactors()
        penalty = factors.calculate_uptime_penalty(
            actual_uptime_percent=Decimal("99.95"),
        )
        assert penalty == Decimal("0")

    def test_uptime_penalty_breach(self):
        """Test penalty calculation for uptime breach."""
        factors = SLAFactors()
        penalty = factors.calculate_uptime_penalty(
            actual_uptime_percent=Decimal("99.5"),  # 0.4% below 99.9%
        )
        # 0.4 * $1000 = $400
        assert penalty == Decimal("400.00")

    def test_customer_tier_multiplier(self):
        """Test that enterprise customers have higher penalties."""
        factors = SLAFactors()

        standard_penalty = factors.calculate_uptime_penalty(
            actual_uptime_percent=Decimal("99.5"),
            customer_tier="professional",
        )

        enterprise_penalty = factors.calculate_uptime_penalty(
            actual_uptime_percent=Decimal("99.5"),
            customer_tier="enterprise",
        )

        assert enterprise_penalty == standard_penalty * 2

    def test_resolution_time_penalty(self):
        """Test resolution time SLA penalty."""
        factors = SLAFactors()
        # Critical has 4h target, if resolved in 8h = 4h breach
        penalty = factors.calculate_resolution_penalty(
            severity="critical",
            resolution_time_hours=8.0,
        )
        # 4 hours * $200/hour = $800
        assert penalty == Decimal("800.00")


class TestCostCalculator:
    """Tests for cost calculator."""

    @pytest.mark.asyncio
    async def test_calculate_incident_cost(self, sample_cost_request):
        """Test calculating incident cost."""
        calculator = CostCalculator()
        cost = await calculator.calculate_incident_cost(sample_cost_request)

        assert cost.incident_id == "INC-001"
        assert cost.service_name == "payments-api"
        assert cost.duration_minutes == 120  # 2 hours
        assert len(cost.responder_costs) == 2
        assert cost.total_cost > Decimal("0")

    @pytest.mark.asyncio
    async def test_responder_costs_calculated(self, sample_cost_request):
        """Test that responder costs are calculated correctly."""
        calculator = CostCalculator()
        cost = await calculator.calculate_incident_cost(sample_cost_request)

        alice_cost = next(
            (r for r in cost.responder_costs if r.responder_name == "Alice"),
            None,
        )
        assert alice_cost is not None
        assert alice_cost.time_spent_minutes == 120
        assert alice_cost.total_cost > Decimal("0")

    @pytest.mark.asyncio
    async def test_revenue_impact_included(self, sample_cost_request):
        """Test that revenue impact is calculated."""
        calculator = CostCalculator()
        cost = await calculator.calculate_incident_cost(sample_cost_request)

        assert cost.total_revenue_impact > Decimal("0")

        # Check breakdown includes revenue impact
        revenue_breakdown = next(
            (b for b in cost.cost_breakdown if b.category == CostCategory.REVENUE_IMPACT),
            None,
        )
        assert revenue_breakdown is not None

    @pytest.mark.asyncio
    async def test_add_sla_penalty(self, sample_incident_cost):
        """Test adding SLA penalty to cost record."""
        calculator = CostCalculator()
        cost = await calculator.add_sla_penalty(
            incident_cost=sample_incident_cost,
            sla_id="SLA-001",
            sla_name="Enterprise Uptime SLA",
            breach_type="uptime",
            target_value="99.9%",
            actual_value="99.5%",
            customer_tier="enterprise",
        )

        assert len(cost.sla_penalties) == 1
        assert cost.sla_penalties[0].sla_name == "Enterprise Uptime SLA"
        assert cost.total_sla_penalties > Decimal("0")

    @pytest.mark.asyncio
    async def test_roi_savings_calculated(self):
        """Test that ROI savings are calculated when MTTR is below baseline."""
        config = get_cost_config()
        config.baseline_mttr_minutes = 120  # 2 hour baseline

        calculator = CostCalculator(config)

        request = CalculateCostRequest(
            incident_id="INC-FAST",
            service_name="api-gateway",
            severity="high",
            incident_started_at=datetime.utcnow() - timedelta(minutes=45),
            incident_resolved_at=datetime.utcnow(),  # 45 min resolution
            responders=[
                {"id": "U001", "name": "Alice", "role": "sre", "time_minutes": 45}
            ],
        )

        cost = await calculator.calculate_incident_cost(request)

        assert cost.baseline_mttr_minutes == 120
        assert cost.actual_mttr_minutes == 45
        assert cost.estimated_savings > Decimal("0")

    @pytest.mark.asyncio
    async def test_finalize_cost(self, sample_incident_cost):
        """Test finalizing a cost record."""
        calculator = CostCalculator()
        cost = await calculator.finalize_cost(
            sample_incident_cost,
            finalized_by="admin@example.com",
        )

        assert cost.is_finalized is True
        assert cost.finalized_by == "admin@example.com"
        assert cost.finalized_at is not None

    @pytest.mark.asyncio
    async def test_roi_analysis(self, clean_store):
        """Test ROI analysis calculation."""
        calculator = CostCalculator()
        now = datetime.utcnow()

        # Create some test incidents
        incidents = []
        for i in range(5):
            cost = IncidentCost(
                cost_id=f"COST-{i}",
                incident_id=f"INC-{i}",
                service_name="api-gateway",
                severity="high",
                incident_started_at=now - timedelta(days=i),
                duration_minutes=45 + (i * 5),  # Varying resolution times
                total_cost=Decimal("1000") + Decimal(str(i * 100)),
                estimated_savings=Decimal("500") if i % 2 == 0 else Decimal("0"),
            )
            incidents.append(cost)
            await clean_store.save(cost)

        analysis = await calculator.calculate_roi_analysis(
            incidents=incidents,
            period_start=now - timedelta(days=30),
            period_end=now,
        )

        assert analysis.total_incidents == 5
        assert analysis.actual_mttr_minutes > 0
        assert analysis.total_savings >= Decimal("0")


class TestCostReportGenerator:
    """Tests for cost report generation."""

    @pytest.mark.asyncio
    async def test_generate_empty_report(self, clean_store):
        """Test generating report with no data."""
        generator = CostReportGenerator(store=clean_store)
        request = GenerateReportRequest(period=ReportPeriod.MONTHLY)

        report = await generator.generate_report(request)

        assert report.total_incidents == 0
        assert report.total_cost == Decimal("0")

    @pytest.mark.asyncio
    async def test_generate_report_with_data(self, clean_store):
        """Test generating report with incident data."""
        generator = CostReportGenerator(store=clean_store)
        now = datetime.utcnow()

        # Add some test costs
        for i in range(3):
            cost = IncidentCost(
                incident_id=f"INC-{i}",
                service_name="api-gateway" if i < 2 else "payments-api",
                severity=["critical", "high", "medium"][i],
                incident_started_at=now - timedelta(days=i),
                duration_minutes=60 + (i * 30),
                total_cost=Decimal("1000") + Decimal(str(i * 500)),
                total_engineer_cost=Decimal("500"),
                total_revenue_impact=Decimal("500") + Decimal(str(i * 500)),
                responder_costs=[
                    ResponderCost(
                        responder_id=f"U00{i}",
                        responder_name=["Alice", "Bob", "Carol"][i],
                        team="platform",
                        total_cost=Decimal("500"),
                        time_spent_minutes=60,
                    )
                ],
            )
            await clean_store.save(cost)

        request = GenerateReportRequest(period=ReportPeriod.MONTHLY)
        report = await generator.generate_report(request)

        assert report.total_incidents == 3
        assert report.total_cost == Decimal("4500")  # 1000 + 1500 + 2000
        assert len(report.service_summaries) == 2
        assert len(report.team_summaries) >= 1

    @pytest.mark.asyncio
    async def test_report_service_filter(self, clean_store):
        """Test filtering report by service."""
        generator = CostReportGenerator(store=clean_store)
        now = datetime.utcnow()

        # Add costs for different services
        await clean_store.save(
            IncidentCost(
                incident_id="INC-1",
                service_name="api-gateway",
                severity="high",
                incident_started_at=now,
                total_cost=Decimal("1000"),
            )
        )
        await clean_store.save(
            IncidentCost(
                incident_id="INC-2",
                service_name="payments-api",
                severity="high",
                incident_started_at=now,
                total_cost=Decimal("2000"),
            )
        )

        request = GenerateReportRequest(
            period=ReportPeriod.MONTHLY,
            services=["payments-api"],
        )
        report = await generator.generate_report(request)

        assert report.total_incidents == 1
        assert report.total_cost == Decimal("2000")

    @pytest.mark.asyncio
    async def test_cost_by_severity(self, clean_store):
        """Test cost breakdown by severity."""
        generator = CostReportGenerator(store=clean_store)
        now = datetime.utcnow()

        await clean_store.save(
            IncidentCost(
                incident_id="INC-C",
                service_name="api",
                severity="critical",
                incident_started_at=now,
                total_cost=Decimal("5000"),
            )
        )
        await clean_store.save(
            IncidentCost(
                incident_id="INC-H",
                service_name="api",
                severity="high",
                incident_started_at=now,
                total_cost=Decimal("2000"),
            )
        )

        request = GenerateReportRequest(period=ReportPeriod.MONTHLY)
        report = await generator.generate_report(request)

        assert report.cost_by_severity["critical"] == Decimal("5000")
        assert report.cost_by_severity["high"] == Decimal("2000")
        assert report.incidents_by_severity["critical"] == 1
        assert report.incidents_by_severity["high"] == 1

    @pytest.mark.asyncio
    async def test_export_to_csv(self, clean_store):
        """Test exporting report to CSV."""
        generator = CostReportGenerator(store=clean_store)

        # Create a simple report
        request = GenerateReportRequest(period=ReportPeriod.MONTHLY)
        report = await generator.generate_report(request)

        csv_content = await generator.export_to_csv(report)

        assert "Cost Report Summary" in csv_content
        assert "Total Incidents" in csv_content
        assert "Cost by Category" in csv_content

    @pytest.mark.asyncio
    async def test_export_to_json(self, clean_store):
        """Test exporting report to JSON."""
        generator = CostReportGenerator(store=clean_store)

        request = GenerateReportRequest(period=ReportPeriod.MONTHLY)
        report = await generator.generate_report(request)

        json_content = await generator.export_to_json(report)

        import json
        data = json.loads(json_content)

        assert "report_id" in data
        assert "total_incidents" in data
        assert "total_cost" in data

    @pytest.mark.asyncio
    async def test_finance_export(self, clean_store):
        """Test exporting for finance systems."""
        generator = CostReportGenerator(store=clean_store)
        now = datetime.utcnow()

        await clean_store.save(
            IncidentCost(
                incident_id="INC-1",
                service_name="api-gateway",
                severity="high",
                incident_started_at=now,
                total_cost=Decimal("1500"),
                responder_costs=[
                    ResponderCost(
                        responder_id="U001",
                        responder_name="Alice",
                        team="platform",
                        total_cost=Decimal("500"),
                        time_spent_minutes=60,
                    )
                ],
            )
        )

        request = GenerateReportRequest(period=ReportPeriod.MONTHLY)
        report = await generator.generate_report(request)

        finance_data = await generator.export_for_finance(report)

        assert finance_data["report_type"] == "incident_cost"
        assert "summary" in finance_data
        assert "department_allocation" in finance_data
        assert "service_cost_centers" in finance_data


class TestDefaultCostFactors:
    """Tests for default cost factor factory."""

    def test_get_engineer_time_factor(self):
        """Test default engineer time factor."""
        factor = DefaultCostFactors.get_engineer_time_factor()

        assert factor.category == CostCategory.ENGINEER_TIME
        assert factor.value == Decimal("150")
        assert factor.unit == "per_hour"
        assert "critical" in factor.severity_multipliers

    def test_get_revenue_impact_factor(self):
        """Test revenue impact factor for service."""
        factor = DefaultCostFactors.get_revenue_impact_factor("payments")

        assert factor.category == CostCategory.REVENUE_IMPACT
        assert factor.value == Decimal("500")
        assert "payments" in factor.applies_to

    def test_get_default_config(self):
        """Test getting default configuration."""
        config = DefaultCostFactors.get_default_config()

        assert config.config_id == "default"
        assert config.is_active is True
        assert len(config.custom_factors) >= 3
        assert config.hourly_rates is not None
        assert config.revenue_factors is not None
        assert config.sla_factors is not None


class TestCostRoutes:
    """Tests for cost API routes."""

    def test_calculate_cost_endpoint(self, client):
        """Test the calculate cost API endpoint."""
        response = client.post(
            "/api/costs/calculate",
            json={
                "incident_id": "INC-API-001",
                "service_name": "api-gateway",
                "severity": "high",
                "incident_started_at": (
                    datetime.utcnow() - timedelta(hours=1)
                ).isoformat(),
                "incident_resolved_at": datetime.utcnow().isoformat(),
                "responders": [
                    {
                        "id": "U001",
                        "name": "Alice",
                        "team": "platform",
                        "role": "sre",
                        "time_minutes": 60,
                    }
                ],
                "affected_users": 1000,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "cost" in data
        assert data["cost"]["incident_id"] == "INC-API-001"
        assert float(data["cost"]["total_cost"]) > 0

    def test_get_cost_endpoint(self, client):
        """Test getting a cost record."""
        # First create a cost
        client.post(
            "/api/costs/calculate",
            json={
                "incident_id": "INC-GET-001",
                "service_name": "api-gateway",
                "severity": "medium",
                "incident_started_at": datetime.utcnow().isoformat(),
            },
        )

        # Then retrieve it
        response = client.get("/api/costs/INC-GET-001")
        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"] == "INC-GET-001"

    def test_get_cost_not_found(self, client):
        """Test getting a non-existent cost record."""
        response = client.get("/api/costs/INC-NONEXISTENT")
        assert response.status_code == 404

    def test_list_costs_endpoint(self, client):
        """Test listing cost records."""
        # Create some costs
        for i in range(3):
            client.post(
                "/api/costs/calculate",
                json={
                    "incident_id": f"INC-LIST-{i}",
                    "service_name": "api-gateway",
                    "severity": "low",
                    "incident_started_at": datetime.utcnow().isoformat(),
                },
            )

        response = client.get("/api/costs")
        assert response.status_code == 200
        data = response.json()
        assert "costs" in data
        assert data["total"] >= 3

    def test_generate_report_endpoint(self, client):
        """Test report generation endpoint."""
        response = client.post(
            "/api/costs/reports/generate",
            json={
                "period": "monthly",
                "include_roi": True,
                "compare_previous": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "report" in data
        assert data["report"]["period"] == "monthly"

    def test_cost_summary_endpoint(self, client):
        """Test quick summary endpoint."""
        response = client.get("/api/costs/reports/summary?period=monthly")

        assert response.status_code == 200
        data = response.json()
        assert "period" in data
        assert "total_incidents" in data
        assert "total_cost" in data

    def test_roi_analysis_endpoint(self, client):
        """Test ROI analysis endpoint."""
        response = client.get("/api/costs/roi/analysis")

        assert response.status_code == 200
        data = response.json()
        assert "analysis_id" in data
        assert "total_savings" in data
        assert "roi_percentage" in data

    def test_get_config_endpoint(self, client):
        """Test getting cost configuration."""
        response = client.get("/api/costs/config")

        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert data["config"]["config_id"] == "default"

    def test_export_csv_endpoint(self, client):
        """Test CSV export endpoint."""
        response = client.get("/api/costs/reports/export/csv?period=monthly")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "Cost Report Summary" in response.text

    def test_finalize_cost_endpoint(self, client):
        """Test finalizing a cost record."""
        # First create a cost
        client.post(
            "/api/costs/calculate",
            json={
                "incident_id": "INC-FINALIZE-001",
                "service_name": "api-gateway",
                "severity": "low",
                "incident_started_at": datetime.utcnow().isoformat(),
            },
        )

        # Then finalize it
        response = client.post(
            "/api/costs/INC-FINALIZE-001/finalize?finalized_by=admin@example.com"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_finalized"] is True
        assert data["finalized_by"] == "admin@example.com"

    def test_cannot_update_finalized_cost(self, client):
        """Test that finalized costs cannot be updated."""
        # Create and finalize a cost
        client.post(
            "/api/costs/calculate",
            json={
                "incident_id": "INC-FINAL-002",
                "service_name": "api-gateway",
                "severity": "low",
                "incident_started_at": datetime.utcnow().isoformat(),
            },
        )
        client.post("/api/costs/INC-FINAL-002/finalize?finalized_by=admin")

        # Try to update
        response = client.put(
            "/api/costs/INC-FINAL-002",
            json={"notes": "Updated notes"},
        )

        assert response.status_code == 400
        assert "finalized" in response.json()["detail"].lower()

    def test_finance_export_endpoint(self, client):
        """Test finance export endpoint."""
        response = client.get("/api/costs/reports/finance-export?period=monthly")

        assert response.status_code == 200
        data = response.json()
        assert data["report_type"] == "incident_cost"
        assert "summary" in data
        assert "department_allocation" in data
