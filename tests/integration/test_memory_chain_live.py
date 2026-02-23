"""
Integration tests for the full incident memory chain against local Supabase.

Requires: `supabase start` running locally.
Run with: make test-integration
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest


# ---------------------------------------------------------------------------
# 1. Incident CRUD against real Supabase
# ---------------------------------------------------------------------------

class TestIncidentCRUD:
    """Verify basic incident operations against live Supabase."""

    def test_insert_incident(self, supabase_client, test_tenant):
        incident_id = str(uuid.uuid4())
        result = supabase_client.table("incidents").insert({
            "id": incident_id,
            "tenant_id": test_tenant,
            "source": "pagerduty",
            "source_id": f"PD-{uuid.uuid4().hex[:8]}",
            "title": "Database connection pool exhausted",
            "service": "postgres-primary",
            "severity": "critical",
            "status": "triggered",
            "triggered_at": datetime.now(UTC).isoformat(),
            "metadata": {"pd_incident_id": "PD-12345"},
        }).execute()

        assert len(result.data) == 1
        assert result.data[0]["title"] == "Database connection pool exhausted"

        # Cleanup
        supabase_client.table("incidents").delete().eq("id", incident_id).execute()

    def test_query_incidents_by_tenant(self, supabase_client, test_tenant, test_incidents):
        result = (
            supabase_client.table("incidents")
            .select("*")
            .eq("tenant_id", test_tenant)
            .execute()
        )
        assert len(result.data) == 5

    def test_query_incidents_by_severity(self, supabase_client, test_tenant, test_incidents):
        result = (
            supabase_client.table("incidents")
            .select("*")
            .eq("tenant_id", test_tenant)
            .eq("severity", "critical")
            .execute()
        )
        assert len(result.data) == 1
        assert result.data[0]["severity"] == "critical"

    def test_query_incidents_by_status(self, supabase_client, test_tenant, test_incidents):
        result = (
            supabase_client.table("incidents")
            .select("*")
            .eq("tenant_id", test_tenant)
            .eq("status", "resolved")
            .execute()
        )
        assert len(result.data) == 3

    def test_resolve_incident(self, supabase_client, test_tenant, test_incidents):
        triggered = [i for i in test_incidents if i["status"] == "triggered"][0]
        now = datetime.now(UTC).isoformat()

        result = (
            supabase_client.table("incidents")
            .update({"status": "resolved", "updated_at": now})
            .eq("id", triggered["id"])
            .execute()
        )
        assert result.data[0]["status"] == "resolved"


# ---------------------------------------------------------------------------
# 2. Analytics queries against real data
# ---------------------------------------------------------------------------

class TestAnalyticsLive:
    """Verify analytics endpoints compute correctly from real DB rows."""

    def test_incident_count_by_period(self, supabase_client, test_tenant, test_incidents):
        seven_days_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        result = (
            supabase_client.table("incidents")
            .select("id", count="exact")
            .eq("tenant_id", test_tenant)
            .gte("created_at", seven_days_ago)
            .execute()
        )
        assert result.count >= 5

    def test_severity_distribution(self, supabase_client, test_tenant, test_incidents):
        result = (
            supabase_client.table("incidents")
            .select("severity")
            .eq("tenant_id", test_tenant)
            .execute()
        )
        severities = [r["severity"] for r in result.data]
        assert "critical" in severities
        assert "high" in severities
        assert len(severities) == 5

    def test_service_breakdown(self, supabase_client, test_tenant, test_incidents):
        result = (
            supabase_client.table("incidents")
            .select("service")
            .eq("tenant_id", test_tenant)
            .execute()
        )
        services = set(r["service"] for r in result.data)
        assert len(services) == 5


# ---------------------------------------------------------------------------
# 3. Incident events (timeline) against real DB
# ---------------------------------------------------------------------------

class TestIncidentEventsLive:
    """Verify incident event tracking."""

    def test_insert_and_query_events(self, supabase_client, test_tenant, test_incidents):
        incident_id = test_incidents[0]["id"]

        events = [
            {
                "id": str(uuid.uuid4()),
                "incident_id": incident_id,
                "tenant_id": test_tenant,
                "event_type": "triggered",
                "message": "Alert fired",
            },
            {
                "id": str(uuid.uuid4()),
                "incident_id": incident_id,
                "tenant_id": test_tenant,
                "event_type": "acknowledged",
                "message": "Acknowledged by oncall",
            },
            {
                "id": str(uuid.uuid4()),
                "incident_id": incident_id,
                "tenant_id": test_tenant,
                "event_type": "resolved",
                "message": "Root cause fixed",
            },
        ]

        for event in events:
            supabase_client.table("incident_events").insert(event).execute()

        result = (
            supabase_client.table("incident_events")
            .select("*")
            .eq("incident_id", incident_id)
            .order("created_at")
            .execute()
        )
        assert len(result.data) == 3
        assert result.data[0]["event_type"] == "triggered"
        assert result.data[2]["event_type"] == "resolved"


# ---------------------------------------------------------------------------
# 4. Insights persistence against real DB
# ---------------------------------------------------------------------------

class TestInsightsLive:
    """Verify insights table persistence."""

    def test_insert_and_query_insight(self, supabase_client, test_tenant):
        insight_id = str(uuid.uuid4())
        supabase_client.table("insights").insert({
            "id": insight_id,
            "tenant_id": test_tenant,
            "insight_type": "pattern",
            "severity": "high",
            "title": "Recurring DB connection failures",
            "description": "Service-a experiences DB connection pool exhaustion every Monday morning",
            "service_name": "service-a",
            "data": {"pattern_count": 5, "frequency": "weekly"},
            "affected_incident_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
            "is_active": True,
        }).execute()

        result = (
            supabase_client.table("insights")
            .select("*")
            .eq("id", insight_id)
            .execute()
        )
        assert len(result.data) == 1
        assert result.data[0]["insight_type"] == "pattern"
        assert result.data[0]["data"]["pattern_count"] == 5

        # Cleanup
        supabase_client.table("insights").delete().eq("id", insight_id).execute()


# ---------------------------------------------------------------------------
# 5. Feedback persistence (memory recall feedback)
# ---------------------------------------------------------------------------

class TestFeedbackLive:
    """Verify feedback table if it exists, otherwise test SQLite path."""

    def test_feedback_sqlite_roundtrip(self, tmp_path):
        """Test the SQLite feedback store directly (no Supabase needed)."""
        from src.memory.feedback import FeedbackStore, ResolutionFeedback

        store = FeedbackStore(str(tmp_path / "feedback.db"))

        import asyncio
        feedback = ResolutionFeedback(
            incident_id="INC-100",
            recalled_incident_id="INC-050",
            feedback="helpful",
            notes="Exact same root cause",
        )
        asyncio.get_event_loop().run_until_complete(store.submit(feedback))

        entries = asyncio.get_event_loop().run_until_complete(
            store.list_for_incident("INC-100")
        )
        assert len(entries) == 1
        assert entries[0].feedback == "helpful"

    def test_feedback_summary_aggregation(self, tmp_path):
        """Test feedback summary used by the learning loop."""
        from src.memory.feedback import FeedbackStore, ResolutionFeedback

        store = FeedbackStore(str(tmp_path / "feedback.db"))

        import asyncio

        for fb_type in ["helpful", "helpful", "not_helpful"]:
            asyncio.get_event_loop().run_until_complete(
                store.submit(ResolutionFeedback(
                    incident_id=f"INC-{fb_type}",
                    recalled_incident_id="INC-RECALLED",
                    feedback=fb_type,
                ))
            )

        summary = asyncio.get_event_loop().run_until_complete(
            store.get_feedback_summary("INC-RECALLED")
        )
        assert summary["helpful"] == 2
        assert summary["not_helpful"] == 1
        assert summary["net_score"] > 0  # 2 helpful > 1 not_helpful


# ---------------------------------------------------------------------------
# 6. Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """Verify data doesn't leak between tenants."""

    def test_incidents_isolated_by_tenant(self, supabase_client, test_tenant, test_incidents):
        other_tenant_id = str(uuid.uuid4())
        supabase_client.table("tenants").insert({
            "id": other_tenant_id,
            "name": "Other Tenant",
            "slug": f"other-{other_tenant_id[:8]}",
            "plan": "free",
        }).execute()

        # Insert incident in other tenant
        other_incident_id = str(uuid.uuid4())
        supabase_client.table("incidents").insert({
            "id": other_incident_id,
            "tenant_id": other_tenant_id,
            "source": "manual",
            "source_id": f"other-{uuid.uuid4().hex[:8]}",
            "title": "Other tenant incident",
            "service": "other-service",
            "severity": "low",
            "status": "triggered",
        }).execute()

        # Query with test_tenant filter should NOT see other tenant's incidents
        result = (
            supabase_client.table("incidents")
            .select("*")
            .eq("tenant_id", test_tenant)
            .execute()
        )
        ids = [r["id"] for r in result.data]
        assert other_incident_id not in ids

        # Cleanup
        supabase_client.table("incidents").delete().eq("id", other_incident_id).execute()
        supabase_client.table("tenants").delete().eq("id", other_tenant_id).execute()
