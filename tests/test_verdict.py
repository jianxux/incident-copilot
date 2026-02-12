"""Tests for the AI Verdict Engine."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.verdict import ConfidenceLevel, Verdict, VerdictEngine
from src.config import Settings


@pytest.fixture
def settings():
    return Settings(anthropic_api_key="test-key", ai_model="claude-3-haiku-20240307")


@pytest.fixture
def engine(settings):
    return VerdictEngine(settings)


@pytest.fixture
def sample_deploys():
    return [
        {
            "sha": "abc123def456",
            "short_sha": "abc123d",
            "author": "alice",
            "message": "Fix auth token validation",
            "timestamp": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "files_changed": ["src/auth/token.py", "src/auth/middleware.py"],
            "additions": 45,
            "deletions": 12,
        },
        {
            "sha": "def789ghi012",
            "short_sha": "def789g",
            "author": "bob",
            "message": "Update dependencies",
            "timestamp": (datetime.utcnow() - timedelta(hours=5)).isoformat(),
            "files_changed": ["requirements.txt"],
            "additions": 3,
            "deletions": 3,
        },
    ]


@pytest.fixture
def sample_log_summary():
    return {
        "top_issues": [
            "ConnectionRefusedError on auth-service:5432",
            "JWT validation failures spiking",
            "Timeout errors on /api/v2/users endpoint",
        ],
        "explanation": "Auth service database connections are being refused, causing cascading JWT failures.",
        "likely_cause": "Database connection pool exhaustion on auth-service",
        "suggested_actions": [
            "Check auth-service database connection pool metrics",
            "Restart auth-service pods",
        ],
    }


class TestVerdictModel:
    """Test Verdict pydantic model."""

    def test_basic_verdict(self):
        v = Verdict(
            most_likely_cause="Database connection pool exhausted",
            confidence=ConfidenceLevel.HIGH,
            evidence="Error rate jumped from 0.1% to 45% after deploy abc123d",
            recommended_action="Roll back deploy abc123d immediately",
        )
        assert v.confidence == ConfidenceLevel.HIGH
        assert v.deploy_correlated is False
        assert v.secondary_action is None

    def test_deploy_correlated_verdict(self):
        v = Verdict(
            most_likely_cause="Auth token validation broken by deploy abc123d",
            confidence=ConfidenceLevel.HIGH,
            evidence="Deploy touched src/auth/token.py 1 hour before alert",
            recommended_action="Roll back deploy abc123d",
            deploy_correlated=True,
            suspect_deploy="abc123d",
        )
        assert v.deploy_correlated is True
        assert v.suspect_deploy == "abc123d"


class TestVerdictEngineFallback:
    """Test fallback verdict generation (no AI client)."""

    def test_fallback_with_deploys(self, sample_deploys):
        engine = VerdictEngine(Settings())  # No API key → no client
        verdict = engine._fallback_verdict(
            title="Auth service errors",
            service_name="auth-service",
            recent_deploys=sample_deploys,
        )
        assert verdict.deploy_correlated is True
        assert "abc123d" in verdict.most_likely_cause
        assert verdict.confidence == ConfidenceLevel.MEDIUM

    def test_fallback_with_log_summary(self, sample_log_summary):
        engine = VerdictEngine(Settings())
        verdict = engine._fallback_verdict(
            title="Auth service errors",
            service_name="auth-service",
            log_summary=sample_log_summary,
        )
        assert "Database connection pool" in verdict.most_likely_cause
        assert verdict.confidence == ConfidenceLevel.LOW

    def test_fallback_bare_minimum(self):
        engine = VerdictEngine(Settings())
        verdict = engine._fallback_verdict(
            title="High error rate",
            service_name="payments-api",
        )
        assert "payments-api" in verdict.most_likely_cause
        assert verdict.confidence == ConfidenceLevel.LOW


class TestVerdictEngineContextBuilder:
    """Test context section building."""

    def test_build_with_all_context(self, engine, sample_deploys, sample_log_summary):
        sections = engine._build_context_sections(
            recent_deploys=sample_deploys,
            log_summary=sample_log_summary,
            metrics={"error_rate": 0.45, "error_rate_baseline": 0.001, "latency_p99_ms": 1200},
            topology={"blast_radius_count": 5, "critical_services_affected": ["gateway", "billing"]},
        )
        assert "RECENT DEPLOYMENTS:" in sections
        assert "LOG ANALYSIS:" in sections
        assert "METRICS:" in sections
        assert "SERVICE TOPOLOGY:" in sections
        assert "alice" in sections
        assert "45.0%" in sections

    def test_build_with_no_context(self, engine):
        sections = engine._build_context_sections()
        assert "No additional context available" in sections

    def test_build_deploys_only(self, engine, sample_deploys):
        sections = engine._build_context_sections(recent_deploys=sample_deploys)
        assert "RECENT DEPLOYMENTS:" in sections
        assert "alice" in sections
        assert "LOG ANALYSIS:" not in sections

    def test_similar_incidents_included(self, engine):
        similar = [
            {
                "title": "Auth outage Jan 15",
                "occurred_at": "2026-01-15",
                "root_cause": "Token validation regression",
                "resolution": "Rolled back deploy def456",
            }
        ]
        sections = engine._build_context_sections(similar_incidents=similar)
        assert "SIMILAR PAST INCIDENTS:" in sections
        assert "Auth outage Jan 15" in sections
        assert "Token validation regression" in sections


class TestVerdictEngineAI:
    """Test AI-powered verdict generation."""

    @pytest.mark.asyncio
    async def test_generate_verdict_success(self, engine, sample_deploys, sample_log_summary):
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = json.dumps(
            {
                "most_likely_cause": "Deploy abc123d broke auth token validation",
                "confidence": "high",
                "evidence": "Error rate spiked from 0.1% to 45% within 30min of deploy",
                "recommended_action": "Roll back deploy abc123d and verify error rate drops",
                "secondary_action": "Check auth-service database connections",
                "deploy_correlated": True,
                "suspect_deploy": "abc123d",
            }
        )
        mock_response.content = [mock_block]

        engine.client = AsyncMock()
        engine.client.messages.create = AsyncMock(return_value=mock_response)

        verdict = await engine.generate_verdict(
            title="Auth service high error rate",
            service_name="auth-service",
            severity="high",
            triggered_at=datetime.utcnow(),
            recent_deploys=sample_deploys,
            log_summary=sample_log_summary,
        )

        assert verdict is not None
        assert verdict.confidence == ConfidenceLevel.HIGH
        assert verdict.deploy_correlated is True
        assert verdict.suspect_deploy == "abc123d"
        assert "abc123d" in verdict.recommended_action

    @pytest.mark.asyncio
    async def test_generate_verdict_ai_failure_falls_back(self, engine, sample_deploys):
        engine.client = AsyncMock()
        engine.client.messages.create = AsyncMock(side_effect=Exception("API error"))

        verdict = await engine.generate_verdict(
            title="Auth service errors",
            service_name="auth-service",
            severity="high",
            triggered_at=datetime.utcnow(),
            recent_deploys=sample_deploys,
        )

        # Should fall back gracefully
        assert verdict is not None
        assert verdict.deploy_correlated is True
        assert "abc123d" in verdict.most_likely_cause

    @pytest.mark.asyncio
    async def test_generate_verdict_no_client(self, sample_deploys):
        engine = VerdictEngine(Settings())  # No API key
        verdict = await engine.generate_verdict(
            title="Service down",
            service_name="payments-api",
            severity="critical",
            triggered_at=datetime.utcnow(),
            recent_deploys=sample_deploys,
        )

        assert verdict is not None
        assert verdict.confidence in [ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW]
