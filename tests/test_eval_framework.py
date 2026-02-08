"""Unit tests for the evaluation framework."""

import pytest
from datetime import datetime

from src.eval.rubric import (
    Rubric,
    RubricScore,
    RubricResult,
    ConfidenceLevel,
    FailureSeverity,
)
from src.eval.synthetic import (
    SyntheticIncident,
    SyntheticIncidentGenerator,
    ScenarioTemplate,
)
from src.eval.harness import (
    EvalHarness,
    EvalResult,
    EvalSummary,
)


class TestRubric:
    """Tests for evaluation rubric."""

    def test_score_root_cause_exact_match(self):
        """Test scoring when root cause is exactly matched."""
        rubric = Rubric()
        score = rubric.score_root_cause(
            predicted="Database connection pool exhausted",
            actual="Database connection pool exhausted",
        )
        
        assert score.score == 1.0
        assert score.dimension == "root_cause"

    def test_score_root_cause_partial_match(self):
        """Test scoring when root cause is partially matched."""
        rubric = Rubric()
        score = rubric.score_root_cause(
            predicted="Connection pool issues detected",
            actual="Database connection pool exhausted due to leak",
            partial_credit=True,
        )
        
        assert score.score > 0.0
        assert score.score < 1.0

    def test_score_root_cause_no_match(self):
        """Test scoring when root cause is completely wrong."""
        rubric = Rubric()
        score = rubric.score_root_cause(
            predicted="Network latency issue",
            actual="Database connection pool exhausted",
        )
        
        assert score.score == 0.0

    def test_score_root_cause_contains_actual(self):
        """Test scoring when prediction contains actual root cause."""
        rubric = Rubric()
        score = rubric.score_root_cause(
            predicted="The issue appears to be a database connection pool exhausted problem causing timeouts",
            actual="database connection pool exhausted",
        )
        
        assert score.score == 1.0

    def test_score_reasoning_all_evidence_found(self):
        """Test reasoning score when all evidence is referenced."""
        rubric = Rubric()
        score = rubric.score_reasoning(
            analysis="Found connection timeout errors and pool exhausted warnings in logs",
            expected_evidence=["connection timeout", "pool exhausted"],
        )
        
        assert score.score == 1.0

    def test_score_reasoning_partial_evidence(self):
        """Test reasoning score when some evidence is referenced."""
        rubric = Rubric()
        score = rubric.score_reasoning(
            analysis="Found connection timeout errors in the logs",
            expected_evidence=["connection timeout", "pool exhausted", "max connections"],
        )
        
        assert score.score == pytest.approx(1/3, rel=0.01)

    def test_score_reasoning_no_evidence(self):
        """Test reasoning score when no evidence is referenced."""
        rubric = Rubric()
        score = rubric.score_reasoning(
            analysis="The system seems to have some issues",
            expected_evidence=["connection timeout", "pool exhausted"],
        )
        
        assert score.score == 0.0

    def test_score_actionability_all_actions_matched(self):
        """Test actionability when all valid actions are recommended."""
        rubric = Rubric()
        score = rubric.score_actionability(
            recommendations=["Check connection pool settings", "Restart the pods"],
            valid_actions=["Check connection pool settings", "Restart the pods"],
        )
        
        assert score.score == 1.0

    def test_score_actionability_partial_match(self):
        """Test actionability when some actions are matched."""
        rubric = Rubric()
        score = rubric.score_actionability(
            recommendations=["Check logs", "Restart pods"],
            valid_actions=["Check connection pool", "Restart pods", "Scale up"],
        )
        
        assert score.score == pytest.approx(1/3, rel=0.01)

    def test_score_actionability_no_recommendations(self):
        """Test actionability when no recommendations provided."""
        rubric = Rubric()
        score = rubric.score_actionability(
            recommendations=[],
            valid_actions=["Check logs"],
        )
        
        assert score.score == 0.0

    def test_failure_severity_correct_answer(self):
        """Test failure severity when answer is correct."""
        rubric = Rubric()
        severity = rubric.assess_failure_severity(
            predicted_root_cause="database connection pool exhausted",
            actual_root_cause="Database connection pool exhausted",
            recommendations=["Restart pods"],
            confidence=ConfidenceLevel.HIGH,
        )
        
        assert severity == FailureSeverity.NONE

    def test_failure_severity_high_confidence_wrong_dangerous(self):
        """Test failure severity when high confidence + wrong + dangerous action."""
        rubric = Rubric()
        severity = rubric.assess_failure_severity(
            predicted_root_cause="Bad deployment",
            actual_root_cause="Upstream service outage",
            recommendations=["Rollback the deployment immediately"],
            confidence=ConfidenceLevel.HIGH,
        )
        
        assert severity == FailureSeverity.CRITICAL

    def test_failure_severity_low_confidence_wrong(self):
        """Test failure severity when low confidence and wrong."""
        rubric = Rubric()
        severity = rubric.assess_failure_severity(
            predicted_root_cause="Unknown issue",
            actual_root_cause="Database issue",
            recommendations=["Check logs"],
            confidence=ConfidenceLevel.LOW,
        )
        
        assert severity == FailureSeverity.MINOR

    def test_evaluate_full_rubric(self):
        """Test full evaluation produces complete result."""
        rubric = Rubric()
        result = rubric.evaluate(
            incident_id="INC-001",
            predicted_root_cause="Database connection pool exhausted",
            actual_root_cause="Database connection pool exhausted due to leak",
            analysis="Found connection timeout errors and pool exhausted warnings",
            recommendations=["Check connection pool", "Restart pods"],
            expected_evidence=["connection timeout", "pool exhausted"],
            valid_actions=["Check connection pool", "Restart pods"],
            confidence=ConfidenceLevel.HIGH,
        )
        
        assert result.incident_id == "INC-001"
        assert result.weighted_score > 0.5
        assert result.passed is True
        assert result.failure_severity == FailureSeverity.NONE

    def test_evaluate_failing_result(self):
        """Test evaluation that should fail."""
        rubric = Rubric()
        result = rubric.evaluate(
            incident_id="INC-002",
            predicted_root_cause="Network issue",
            actual_root_cause="Database connection pool exhausted",
            analysis="Seems like networking problem",
            recommendations=["Check network"],
            expected_evidence=["connection timeout", "pool exhausted"],
            valid_actions=["Check connection pool", "Restart pods"],
            confidence=ConfidenceLevel.HIGH,
        )
        
        assert result.weighted_score < 0.6
        assert result.passed is False

    def test_rubric_result_to_dict(self):
        """Test RubricResult serialization."""
        rubric = Rubric()
        result = rubric.evaluate(
            incident_id="INC-003",
            predicted_root_cause="test",
            actual_root_cause="test",
            analysis="test analysis",
            recommendations=["action"],
            expected_evidence=["evidence"],
            valid_actions=["action"],
        )
        
        d = result.to_dict()
        assert "incident_id" in d
        assert "weighted_score" in d
        assert "passed" in d
        assert "dimensions" in d


class TestSyntheticIncidentGenerator:
    """Tests for synthetic incident generator."""

    def test_generate_incident(self):
        """Test generating a single incident."""
        gen = SyntheticIncidentGenerator(seed=42)
        incident = gen.generate()
        
        assert incident.incident_id is not None
        assert incident.title is not None
        assert incident.service_name is not None
        assert incident.actual_root_cause is not None
        assert len(incident.logs) > 0
        assert len(incident.expected_evidence) > 0
        assert len(incident.valid_actions) > 0

    def test_generate_specific_scenario(self):
        """Test generating specific scenario type."""
        gen = SyntheticIncidentGenerator(seed=42)
        incident = gen.generate(scenario_name="database_connection_exhaustion")
        
        assert incident.scenario_type == "database_connection_exhaustion"
        assert "connection" in incident.actual_root_cause.lower() or "database" in incident.actual_root_cause.lower()

    def test_generate_specific_service(self):
        """Test generating incident for specific service."""
        gen = SyntheticIncidentGenerator(seed=42)
        incident = gen.generate(service_name="my-custom-service")
        
        assert incident.service_name == "my-custom-service"

    def test_generate_with_incident_time(self):
        """Test generating incident at specific time."""
        gen = SyntheticIncidentGenerator(seed=42)
        custom_time = datetime(2024, 6, 15, 12, 0, 0)
        incident = gen.generate(incident_time=custom_time)
        
        assert incident.triggered_at == custom_time

    def test_generate_batch(self):
        """Test generating batch of incidents."""
        gen = SyntheticIncidentGenerator(seed=42)
        incidents = gen.generate_batch(count=20)
        
        assert len(incidents) == 20
        # Should cover all scenarios at least once
        scenarios = {i.scenario_type for i in incidents}
        assert len(scenarios) >= 5

    def test_generate_deterministic_with_seed(self):
        """Test that same seed produces consistent results in sequence."""
        gen = SyntheticIncidentGenerator(seed=123)
        
        # Generate two incidents
        incident1 = gen.generate()
        incident2 = gen.generate()
        
        # Reset with same seed
        gen2 = SyntheticIncidentGenerator(seed=123)
        incident1_again = gen2.generate()
        incident2_again = gen2.generate()
        
        # First incidents should match (same seed, same call order)
        assert incident1.scenario_type == incident1_again.scenario_type
        assert incident1.service_name == incident1_again.service_name

    def test_incident_has_logs(self):
        """Test that generated incident has realistic logs."""
        gen = SyntheticIncidentGenerator(seed=42)
        incident = gen.generate()
        
        assert len(incident.logs) > 50  # Should have decent number of logs
        # Logs should contain error patterns
        error_logs = [l for l in incident.logs if "ERROR" in l or "FATAL" in l or "WARN" in l]
        assert len(error_logs) > 0

    def test_incident_has_metrics(self):
        """Test that generated incident has metrics."""
        gen = SyntheticIncidentGenerator(seed=42)
        incident = gen.generate()
        
        assert len(incident.metrics) > 0
        for metric_name, series in incident.metrics.items():
            assert len(series) > 0
            # Each point should be (timestamp, value)
            assert len(series[0]) == 2

    def test_incident_has_deploys(self):
        """Test that generated incident has deployment history."""
        gen = SyntheticIncidentGenerator(seed=42)
        incident = gen.generate()
        
        assert len(incident.recent_deploys) > 0
        deploy = incident.recent_deploys[0]
        assert "sha" in deploy
        assert "message" in deploy
        assert "author" in deploy

    def test_all_scenarios_accessible(self):
        """Test that all scenario templates are valid."""
        gen = SyntheticIncidentGenerator()
        
        for scenario in gen.SCENARIOS:
            incident = gen.generate(scenario_name=scenario.name)
            assert incident is not None
            assert incident.scenario_type == scenario.name


class TestEvalHarness:
    """Tests for evaluation harness."""

    @pytest.fixture
    def sample_incidents(self):
        """Generate sample incidents for testing."""
        gen = SyntheticIncidentGenerator(seed=42)
        return gen.generate_batch(count=5)

    def test_harness_initialization(self):
        """Test harness initialization."""
        harness = EvalHarness(copilot=None)
        
        assert harness.copilot is None
        assert harness.rubric is not None
        assert harness.output_dir.exists()

    @pytest.mark.asyncio
    async def test_run_eval_mock(self, sample_incidents):
        """Test running evaluation with mock copilot."""
        harness = EvalHarness(copilot=None)
        results = await harness.run_eval(sample_incidents)
        
        assert len(results) == 5
        for result in results:
            assert result.incident_id is not None
            assert result.rubric is not None
            assert result.latency_ms >= 0

    def test_summary_generation(self):
        """Test summary generation from results."""
        harness = EvalHarness(copilot=None)
        
        # Manually add some results
        harness.results = [
            EvalResult(
                incident_id="INC-001",
                scenario_type="database_connection_exhaustion",
                difficulty="medium",
                predicted_root_cause="DB issue",
                analysis="Found errors",
                recommendations=["Check DB"],
                confidence=ConfidenceLevel.HIGH,
                latency_ms=100,
                tokens_used=1000,
                rubric=Rubric().evaluate(
                    incident_id="INC-001",
                    predicted_root_cause="DB issue",
                    actual_root_cause="DB issue",
                    analysis="Found errors",
                    recommendations=["Check DB"],
                    expected_evidence=["error"],
                    valid_actions=["Check DB"],
                ),
            ),
            EvalResult(
                incident_id="INC-002",
                scenario_type="bad_deployment",
                difficulty="easy",
                predicted_root_cause="Unknown",
                analysis="Not sure",
                recommendations=[],
                confidence=ConfidenceLevel.LOW,
                latency_ms=200,
                tokens_used=500,
                rubric=Rubric().evaluate(
                    incident_id="INC-002",
                    predicted_root_cause="Unknown",
                    actual_root_cause="Bad deploy",
                    analysis="Not sure",
                    recommendations=[],
                    expected_evidence=["deploy"],
                    valid_actions=["Rollback"],
                ),
            ),
        ]
        
        summary = harness.summary()
        
        assert summary.total_incidents == 2
        assert summary.passed >= 0
        assert summary.failed >= 0
        assert summary.passed + summary.failed == 2
        assert summary.avg_latency_ms == 150
        assert summary.avg_tokens == 750
        assert "database_connection_exhaustion" in summary.by_scenario
        assert "bad_deployment" in summary.by_scenario

    def test_summary_empty_results(self):
        """Test summary with no results."""
        harness = EvalHarness(copilot=None)
        summary = harness.summary()
        
        assert summary.total_incidents == 0
        assert summary.passed == 0
        assert summary.failed == 0

    def test_summary_to_dict(self):
        """Test summary serialization."""
        harness = EvalHarness(copilot=None)
        harness.results = [
            EvalResult(
                incident_id="INC-001",
                scenario_type="test",
                difficulty="easy",
                predicted_root_cause="test",
                analysis="test",
                recommendations=[],
                confidence=ConfidenceLevel.MEDIUM,
                latency_ms=100,
                tokens_used=500,
                rubric=Rubric().evaluate(
                    incident_id="INC-001",
                    predicted_root_cause="test",
                    actual_root_cause="test",
                    analysis="test",
                    recommendations=[],
                    expected_evidence=[],
                    valid_actions=[],
                ),
            ),
        ]
        
        d = harness.summary().to_dict()
        
        assert "total" in d
        assert "passed" in d
        assert "failed" in d
        assert "pass_rate" in d
        assert "avg_score" in d


class TestEvalResult:
    """Tests for EvalResult."""

    def test_eval_result_to_dict(self):
        """Test EvalResult serialization."""
        result = EvalResult(
            incident_id="INC-001",
            scenario_type="test",
            difficulty="easy",
            predicted_root_cause="Test cause",
            analysis="Test analysis",
            recommendations=["Action 1", "Action 2"],
            confidence=ConfidenceLevel.HIGH,
            latency_ms=150,
            tokens_used=1200,
            rubric=Rubric().evaluate(
                incident_id="INC-001",
                predicted_root_cause="Test cause",
                actual_root_cause="Test cause",
                analysis="Test analysis",
                recommendations=["Action 1"],
                expected_evidence=["evidence"],
                valid_actions=["Action 1"],
            ),
        )
        
        d = result.to_dict()
        
        assert d["incident_id"] == "INC-001"
        assert d["scenario_type"] == "test"
        assert d["confidence"] == "high"
        assert d["latency_ms"] == 150
        assert d["tokens_used"] == 1200
        assert "rubric" in d
