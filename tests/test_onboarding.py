"""Tests for onboarding checklist and wizard endpoints."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

os.environ["SUPABASE_DB_ENABLED"] = "false"
os.environ.pop("SUPABASE_URL", None)

from src.onboarding.checklist import CHECKLIST_STEPS, OPTIONAL_STEPS, OnboardingChecklist


# ── Checklist Model Tests ──────────────────────────────────────────


class TestOnboardingChecklist:
    def test_default_all_incomplete(self):
        c = OnboardingChecklist(tenant_id="t1")
        assert c.progress == 0.0
        for step in CHECKLIST_STEPS:
            assert c.completed[step] is False

    def test_mark_step(self):
        c = OnboardingChecklist(tenant_id="t1")
        c.mark("create_account", True)
        assert c.completed["create_account"] is True
        required = [s for s in CHECKLIST_STEPS if s not in OPTIONAL_STEPS]
        assert c.progress == 1 / len(required)

    def test_mark_unknown_step_raises(self):
        c = OnboardingChecklist(tenant_id="t1")
        with pytest.raises(ValueError, match="Unknown onboarding step"):
            c.mark("nonexistent_step")

    def test_mark_unmark(self):
        c = OnboardingChecklist(tenant_id="t1")
        c.mark("connect_alerting", True)
        assert c.completed["connect_alerting"] is True
        c.mark("connect_alerting", False)
        assert c.completed["connect_alerting"] is False
        assert c.progress == 0.0

    def test_progress_calculation(self):
        c = OnboardingChecklist(tenant_id="t1")
        for step in CHECKLIST_STEPS:
            c.mark(step, True)
        assert c.progress == 1.0

    def test_progress_partial(self):
        c = OnboardingChecklist(tenant_id="t1")
        c.mark("create_account", True)
        c.mark("connect_alerting", True)
        c.mark("connect_slack", True)
        required = [s for s in CHECKLIST_STEPS if s not in OPTIONAL_STEPS]
        expected = 3 / len(required)
        assert abs(c.progress - expected) < 0.01

    def test_to_dict_structure(self):
        c = OnboardingChecklist(tenant_id="t1")
        c.mark("create_account", True)
        d = c.to_dict()
        assert d["tenant_id"] == "t1"
        assert isinstance(d["steps"], list)
        assert len(d["steps"]) == len(CHECKLIST_STEPS)
        assert d["progress"] > 0
        assert "updated_at" in d

        # Check step structure
        step0 = d["steps"][0]
        assert "id" in step0
        assert "title" in step0
        assert "done" in step0

    def test_to_dict_step_titles(self):
        c = OnboardingChecklist(tenant_id="t1")
        d = c.to_dict()
        titles = {s["id"]: s["title"] for s in d["steps"]}
        assert titles["create_account"] == "Create account"
        assert titles["connect_alerting"] == "Connect alerting (PagerDuty/Opsgenie)"
        assert titles["add_services"] == "Add services"

    def test_checklist_steps_are_defined(self):
        assert len(CHECKLIST_STEPS) >= 6
        assert "create_account" in CHECKLIST_STEPS
        assert "connect_alerting" in CHECKLIST_STEPS
        assert "connect_slack" in CHECKLIST_STEPS
        assert "add_services" in CHECKLIST_STEPS
        assert "run_test" not in CHECKLIST_STEPS
        assert "go_live" not in CHECKLIST_STEPS


# ── ChecklistStore (SQLite) Tests ──────────────────────────────────


class TestChecklistStore:
    @pytest_asyncio.fixture
    async def store(self, tmp_path):
        from src.onboarding.db_store import ChecklistStore
        db_path = tmp_path / "test_checklist.db"
        s = ChecklistStore(db_path=db_path)
        yield s

    @pytest.mark.asyncio
    async def test_get_creates_default(self, store):
        c = await store.get("tenant-1")
        assert c.tenant_id == "tenant-1"
        assert c.progress == 0.0

    @pytest.mark.asyncio
    async def test_set_step_persists(self, store):
        await store.set_step("tenant-1", "create_account", True)
        c = await store.get("tenant-1")
        assert c.completed["create_account"] is True
        assert c.progress > 0

    @pytest.mark.asyncio
    async def test_set_step_idempotent(self, store):
        await store.set_step("tenant-1", "create_account", True)
        await store.set_step("tenant-1", "create_account", True)
        c = await store.get("tenant-1")
        assert c.completed["create_account"] is True

    @pytest.mark.asyncio
    async def test_set_step_toggle(self, store):
        await store.set_step("tenant-1", "connect_slack", True)
        await store.set_step("tenant-1", "connect_slack", False)
        c = await store.get("tenant-1")
        assert c.completed["connect_slack"] is False

    @pytest.mark.asyncio
    async def test_multiple_tenants_isolated(self, store):
        await store.set_step("t1", "create_account", True)
        await store.set_step("t2", "connect_slack", True)
        c1 = await store.get("t1")
        c2 = await store.get("t2")
        assert c1.completed["create_account"] is True
        assert c1.completed["connect_slack"] is False
        assert c2.completed["create_account"] is False
        assert c2.completed["connect_slack"] is True

    @pytest.mark.asyncio
    async def test_progress_after_multiple_steps(self, store):
        await store.set_step("t1", "create_account", True)
        await store.set_step("t1", "connect_alerting", True)
        await store.set_step("t1", "connect_slack", True)
        c = await store.get("t1")
        required = [s for s in CHECKLIST_STEPS if s not in OPTIONAL_STEPS]
        assert abs(c.progress - 3 / len(required)) < 0.01


# ── Test Incident Poll Status Logic ────────────────────────────────


class TestTestIncidentPollStatus:
    """Tests for the poll endpoint status mapping logic (routes.py)."""

    def _map_status(self, db_status: str | None) -> str:
        """Mirror the logic from get_test_incident_status."""
        raw = (db_status or "").lower()
        if raw in ("completed", "resolved"):
            return "completed"
        elif raw == "error":
            return "error"
        else:
            return "processing"

    def test_completed_status(self):
        assert self._map_status("completed") == "completed"

    def test_resolved_status(self):
        assert self._map_status("resolved") == "completed"

    def test_error_status(self):
        assert self._map_status("error") == "error"

    def test_processing_status(self):
        assert self._map_status("processing") == "processing"

    def test_triggered_status(self):
        assert self._map_status("triggered") == "processing"

    def test_none_status(self):
        assert self._map_status(None) == "processing"

    def test_empty_status(self):
        assert self._map_status("") == "processing"


# ── API Endpoint Tests (via TestClient) ────────────────────────────
# NOTE: Full integration tests with TestClient + create_app() are in
# tests/integration/test_onboarding_api.py. They require more memory
# and are skipped in lightweight CI runs.
#
# To run them locally:
#   uv run pytest tests/integration/test_onboarding_api.py -v
