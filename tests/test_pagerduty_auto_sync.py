"""Tests for automatic PagerDuty background sync on dashboard load."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.pagerduty_sync import (
    _PD_SYNC_INTERVAL,
    _background_pd_sync,
    _build_pd_upsert_rows,
    _maybe_trigger_pd_sync,
    _pd_id_to_uuid,
    _pd_sync_timestamps,
)


@pytest.fixture(autouse=True)
def _clear_sync_timestamps():
    """Reset the global sync timestamps between tests."""
    _pd_sync_timestamps.clear()
    yield
    _pd_sync_timestamps.clear()


# ---------------------------------------------------------------------------
# _build_pd_upsert_rows — row building logic
# ---------------------------------------------------------------------------


class TestBuildPdUpsertRows:
    """Tests for the shared PagerDuty incident row builder."""

    def test_basic_incident(self):
        pd_incidents = [
            {
                "id": "P123",
                "title": "High CPU on web-1",
                "status": "triggered",
                "urgency": "high",
                "created_at": "2026-02-21T10:00:00Z",
                "service": {"summary": "web-service"},
                "html_url": "https://pd.com/incidents/P123",
                "incident_number": 42,
                "assignments": [],
                "escalation_policy": {"summary": "Default"},
            }
        ]
        rows, summaries = _build_pd_upsert_rows(pd_incidents, "tenant-1")
        assert len(rows) == 1
        assert len(summaries) == 1
        row = rows[0]
        # id is a deterministic UUID5 derived from the PD incident ID
        assert row["id"] == _pd_id_to_uuid("P123")
        assert row["tenant_id"] == "tenant-1"
        assert row["service"] == "web-service"
        assert row["severity"] == "high"
        assert row["status"] == "triggered"
        assert row["source"] == "pagerduty"
        assert row["source_id"] == "P123"

    def test_resolved_status_mapping(self):
        last_change = "2026-02-21T08:30:00Z"
        pd_incidents = [
            {
                "id": "P456",
                "title": "Resolved issue",
                "status": "resolved",
                "urgency": "low",
                "created_at": "2026-02-21T08:00:00Z",
                "last_status_change_at": last_change,
                "resolved_at": "2026-02-21T08:20:00Z",
                "service": {"summary": "api"},
                "assignments": [],
                "escalation_policy": {},
            }
        ]
        rows, _ = _build_pd_upsert_rows(pd_incidents, "t1")
        assert rows[0]["status"] == "resolved"
        assert rows[0]["severity"] == "low"
        assert rows[0]["processed_at"] == "2026-02-21T08:30:00+00:00"
        assert rows[0]["resolved_at"] == "2026-02-21T08:30:00+00:00"
        assert rows[0]["metadata"]["resolved_at"] == "2026-02-21T08:30:00+00:00"

    def test_resolved_timestamp_falls_back_to_resolved_at(self):
        pd_incidents = [
            {
                "id": "P457",
                "title": "Resolved issue fallback",
                "status": "resolved",
                "urgency": "low",
                "created_at": "2026-02-21T08:00:00Z",
                "resolved_at": "2026-02-21T08:45:00Z",
                "service": {"summary": "api"},
                "assignments": [],
                "escalation_policy": {},
            }
        ]
        rows, _ = _build_pd_upsert_rows(pd_incidents, "t1")
        assert rows[0]["processed_at"] == "2026-02-21T08:45:00+00:00"
        assert rows[0]["resolved_at"] == "2026-02-21T08:45:00+00:00"

    def test_acknowledged_status_mapping(self):
        pd_incidents = [
            {
                "id": "P789",
                "title": "Acked",
                "status": "acknowledged",
                "urgency": "high",
                "created_at": "2026-02-21T09:00:00Z",
                "service": {"summary": "db"},
                "assignments": [],
                "escalation_policy": {},
            }
        ]
        rows, _ = _build_pd_upsert_rows(pd_incidents, "t1")
        assert rows[0]["status"] == "acknowledged"

    def test_skips_empty_id(self):
        pd_incidents = [{"id": "", "title": "No ID"}]
        rows, summaries = _build_pd_upsert_rows(pd_incidents, "t1")
        assert len(rows) == 0
        assert len(summaries) == 0

    def test_metadata_includes_assignments(self):
        pd_incidents = [
            {
                "id": "P111",
                "title": "Assigned",
                "status": "triggered",
                "urgency": "high",
                "created_at": "2026-02-21T10:00:00Z",
                "service": {"summary": "svc"},
                "assignments": [
                    {"assignee": {"summary": "Alice"}},
                    {"assignee": {"summary": "Bob"}},
                ],
                "escalation_policy": {"summary": "Oncall Team"},
            }
        ]
        rows, _ = _build_pd_upsert_rows(pd_incidents, "t1")
        meta = rows[0]["metadata"]
        assert meta["assigned_to"] == ["Alice", "Bob"]
        assert meta["escalation_policy"] == "Oncall Team"
        assert meta["provider"] == "pagerduty"

    def test_multiple_incidents_batch(self):
        pd_incidents = [
            {
                "id": f"P{i}",
                "title": f"Inc {i}",
                "status": "triggered",
                "urgency": "low",
                "created_at": "2026-02-21T10:00:00Z",
                "service": {"summary": f"svc-{i}"},
                "assignments": [],
                "escalation_policy": {},
            }
            for i in range(25)
        ]
        rows, summaries = _build_pd_upsert_rows(pd_incidents, "t1")
        assert len(rows) == 25
        assert len(summaries) == 25

    def test_missing_service_defaults_to_empty(self):
        pd_incidents = [
            {
                "id": "P222",
                "title": "No service",
                "status": "triggered",
                "urgency": "low",
                "created_at": "2026-02-21T10:00:00Z",
                "assignments": [],
                "escalation_policy": {},
            }
        ]
        rows, _ = _build_pd_upsert_rows(pd_incidents, "t1")
        assert rows[0]["service"] == ""

    def test_bad_date_defaults_to_now(self):
        pd_incidents = [
            {
                "id": "P333",
                "title": "Bad date",
                "status": "triggered",
                "urgency": "low",
                "created_at": "not-a-date",
                "service": {"summary": "svc"},
                "assignments": [],
                "escalation_policy": {},
            }
        ]
        rows, _ = _build_pd_upsert_rows(pd_incidents, "t1")
        # Should not raise, triggered_at should be set
        assert rows[0]["triggered_at"] is not None


# ---------------------------------------------------------------------------
# _maybe_trigger_pd_sync — debounce logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_call_within_interval_skips():
    """A call within 5 min of the last sync should NOT trigger another sync."""
    _pd_sync_timestamps["tenant-1"] = time.time()

    with patch("src.integrations.pagerduty_sync._background_pd_sync", new_callable=AsyncMock) as mock_sync:
        result = await _maybe_trigger_pd_sync("tenant-1")

    mock_sync.assert_not_called()
    assert result is False


@pytest.mark.asyncio
async def test_call_after_interval_triggers_sync():
    """A call after the debounce interval should trigger sync again."""
    _pd_sync_timestamps["tenant-1"] = time.time() - _PD_SYNC_INTERVAL - 1

    with patch("src.integrations.pagerduty_sync._background_pd_sync", new_callable=AsyncMock):
        with patch("src.integrations.pagerduty_sync.asyncio.create_task") as mock_task:
            await _maybe_trigger_pd_sync("tenant-1")

    # Subsequent sync fires as background task
    mock_task.assert_called_once()


@pytest.mark.asyncio
async def test_different_tenants_sync_independently():
    """Each tenant has its own debounce timestamp."""
    _pd_sync_timestamps["tenant-1"] = time.time()  # recently synced

    with patch("src.integrations.pagerduty_sync._background_pd_sync", new_callable=AsyncMock) as mock_sync:
        with patch("src.integrations.pagerduty_sync.asyncio.create_task"):
            await _maybe_trigger_pd_sync("tenant-1")  # should skip
            await _maybe_trigger_pd_sync("tenant-2")  # should trigger (first sync)

    # tenant-2 is first sync so it's awaited directly
    mock_sync.assert_called_once()


# ---------------------------------------------------------------------------
# _background_pd_sync — resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_returns_silently_when_no_token():
    """If no PD token is found, the sync should return without error."""
    mock_token_store = MagicMock()
    mock_token_store.get_token = AsyncMock(return_value=None)

    with patch(
        "src.integrations.oauth_tokens.oauth_token_store",
        mock_token_store,
    ):
        await _background_pd_sync("tenant-no-pd")


@pytest.mark.asyncio
async def test_sync_failure_does_not_raise():
    """If the PD API call fails, the sync catches the exception silently."""
    mock_token_store = MagicMock()
    mock_token_rec = MagicMock()
    mock_token_rec.access_token = "xoxb-fake"
    mock_token_store.get_token = AsyncMock(return_value=mock_token_rec)

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "src.integrations.oauth_tokens.oauth_token_store",
            mock_token_store,
        ),
        patch("httpx.AsyncClient", return_value=mock_client_instance),
    ):
        await _background_pd_sync("tenant-err")


@pytest.mark.asyncio
async def test_sync_success_updates_timestamp():
    """A successful sync should update the timestamp for the tenant."""
    mock_token_store = MagicMock()
    mock_token_rec = MagicMock()
    mock_token_rec.access_token = "xoxb-fake"
    mock_token_store.get_token = AsyncMock(return_value=mock_token_rec)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"incidents": []}
    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    _pd_sync_timestamps.pop("tenant-ok", None)

    with (
        patch(
            "src.integrations.oauth_tokens.oauth_token_store",
            mock_token_store,
        ),
        patch("httpx.AsyncClient", return_value=mock_client_instance),
    ):
        await _background_pd_sync("tenant-ok")

    assert "tenant-ok" in _pd_sync_timestamps
    assert _pd_sync_timestamps["tenant-ok"] > 0


class TestFirstSyncTimeout:
    """First PD sync should not block indefinitely."""

    @pytest.mark.asyncio
    async def test_first_sync_has_timeout(self):
        """If PD API is slow, first sync should timeout and not block forever."""

        async def slow_sync(tenant_id):
            await asyncio.sleep(30)

        with patch("src.integrations.pagerduty_sync._background_pd_sync", side_effect=slow_sync):
            with patch("src.integrations.pagerduty_sync._pd_sync_timestamps", {}):
                start = time.time()
                await _maybe_trigger_pd_sync("tenant-slow")
                elapsed = time.time() - start
                assert elapsed < 13, f"First sync took {elapsed}s, should timeout at ~10s"
