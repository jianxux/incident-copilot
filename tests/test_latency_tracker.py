"""Tests for the latency tracking system."""

import time
from datetime import datetime, timedelta

import pytest

from src.metrics.latency_tracker import LatencyReport, LatencyTracker, Phase


class TestLatencyTracker:
    """Test the LatencyTracker."""

    def test_basic_tracking(self):
        tracker = LatencyTracker("INC-1", "auth-service")

        tracker.start(Phase.WEBHOOK_RECEIVED)
        tracker.end(Phase.WEBHOOK_RECEIVED)

        tracker.start(Phase.CARD_DELIVERED)
        time.sleep(0.01)  # Simulate work
        tracker.end(Phase.CARD_DELIVERED)

        report = tracker.report()
        assert report.incident_id == "INC-1"
        assert report.service_name == "auth-service"
        assert report.total_ms is not None
        assert report.total_ms >= 10  # At least 10ms from sleep

    def test_within_budget(self):
        tracker = LatencyTracker("INC-1", "auth-service", budget_ms=5000)

        tracker.start(Phase.WEBHOOK_RECEIVED)
        tracker.end(Phase.WEBHOOK_RECEIVED)

        tracker.start(Phase.CARD_DELIVERED)
        tracker.end(Phase.CARD_DELIVERED)

        report = tracker.report()
        assert report.within_budget is True

    def test_phase_timing(self):
        tracker = LatencyTracker("INC-1", "auth-service")

        tracker.start(Phase.SCM_FETCH)
        time.sleep(0.02)
        tracker.end(Phase.SCM_FETCH)

        report = tracker.report()
        scm = report.phases.get(Phase.SCM_FETCH.value)
        assert scm is not None
        assert scm.duration_ms >= 15  # ~20ms
        assert scm.success is True

    def test_phase_error_tracking(self):
        tracker = LatencyTracker("INC-1", "auth-service")

        tracker.start(Phase.LOG_FETCH)
        tracker.end(Phase.LOG_FETCH, success=False, error="connection timeout")

        report = tracker.report()
        log_phase = report.phases.get(Phase.LOG_FETCH.value)
        assert log_phase.success is False
        assert log_phase.error == "connection timeout"

    def test_context_manager(self):
        tracker = LatencyTracker("INC-1", "auth-service")

        with tracker.track(Phase.RUNBOOK_LINK):
            time.sleep(0.01)

        report = tracker.report()
        phase = report.phases.get(Phase.RUNBOOK_LINK.value)
        assert phase is not None
        assert phase.success is True
        assert phase.duration_ms >= 5

    def test_context_manager_with_error(self):
        tracker = LatencyTracker("INC-1", "auth-service")

        with pytest.raises(ValueError):
            with tracker.track(Phase.AI_SUMMARIZE):
                raise ValueError("model error")

        report = tracker.report()
        phase = report.phases.get(Phase.AI_SUMMARIZE.value)
        assert phase.success is False
        assert "model error" in phase.error

    def test_alert_to_delivery(self):
        tracker = LatencyTracker("INC-1", "auth-service")
        fired_at = datetime.utcnow() - timedelta(seconds=5)
        tracker.set_alert_fired_at(fired_at)

        tracker.start(Phase.WEBHOOK_RECEIVED)
        tracker.end(Phase.WEBHOOK_RECEIVED)

        tracker.start(Phase.CARD_DELIVERED)
        tracker.end(Phase.CARD_DELIVERED)

        report = tracker.report()
        assert report.alert_to_delivery_ms is not None
        assert report.alert_to_delivery_ms >= 5000  # At least 5s from the timedelta

    def test_summary_output(self):
        tracker = LatencyTracker("INC-1", "auth-service")
        tracker.start(Phase.WEBHOOK_RECEIVED)
        tracker.end(Phase.WEBHOOK_RECEIVED)
        tracker.start(Phase.CARD_DELIVERED)
        tracker.end(Phase.CARD_DELIVERED)

        report = tracker.report()
        summary = report.summary()

        assert "incident_id" in summary
        assert "total_ms" in summary
        assert "within_budget" in summary
        assert "phases" in summary

    def test_multiple_phases(self):
        tracker = LatencyTracker("INC-1", "auth-service")

        tracker.start(Phase.WEBHOOK_RECEIVED)
        tracker.end(Phase.WEBHOOK_RECEIVED)

        tracker.start(Phase.CONTEXT_FETCH_START)
        tracker.start(Phase.SCM_FETCH)
        tracker.end(Phase.SCM_FETCH)
        tracker.start(Phase.LOG_FETCH)
        tracker.end(Phase.LOG_FETCH)
        tracker.end(Phase.CONTEXT_FETCH_START)

        tracker.start(Phase.AI_VERDICT)
        tracker.end(Phase.AI_VERDICT)

        tracker.start(Phase.CARD_DELIVERED)
        tracker.end(Phase.CARD_DELIVERED)

        report = tracker.report()
        assert len(report.phases) == 6
        assert report.total_ms is not None


class TestLatencyReport:
    """Test LatencyReport model."""

    def test_budget_default(self):
        report = LatencyReport(incident_id="INC-1", service_name="svc")
        assert report.budget_ms == 10000

    def test_finalize_no_phases(self):
        report = LatencyReport(incident_id="INC-1", service_name="svc")
        report.finalize()
        assert report.total_ms is None
        assert report.within_budget is None
