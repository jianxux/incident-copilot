"""Tests for automatic PagerDuty background sync on dashboard load."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.web.routes import (
    _PD_SYNC_INTERVAL,
    _background_pd_sync,
    _maybe_trigger_pd_sync,
    _pd_sync_timestamps,
)


@pytest.fixture(autouse=True)
def _clear_sync_timestamps():
    """Reset the global sync timestamps between tests."""
    _pd_sync_timestamps.clear()
    yield
    _pd_sync_timestamps.clear()


# ---------------------------------------------------------------------------
# _maybe_trigger_pd_sync — debounce logic
# ---------------------------------------------------------------------------


def test_first_call_triggers_sync():
    """First call for a tenant should launch a background sync task."""
    with patch("src.web.routes.asyncio.create_task") as mock_create:
        _maybe_trigger_pd_sync("tenant-1")

    mock_create.assert_called_once()
    # Timestamp should be set
    assert "tenant-1" in _pd_sync_timestamps


def test_second_call_within_interval_skips():
    """A call within 5 min of the last sync should NOT trigger another sync."""
    _pd_sync_timestamps["tenant-1"] = time.time()

    with patch("src.web.routes.asyncio.create_task") as mock_create:
        _maybe_trigger_pd_sync("tenant-1")

    mock_create.assert_not_called()


def test_call_after_interval_triggers_sync():
    """A call after the debounce interval should trigger sync again."""
    _pd_sync_timestamps["tenant-1"] = time.time() - _PD_SYNC_INTERVAL - 1

    with patch("src.web.routes.asyncio.create_task") as mock_create:
        _maybe_trigger_pd_sync("tenant-1")

    mock_create.assert_called_once()


def test_different_tenants_sync_independently():
    """Each tenant has its own debounce timestamp."""
    _pd_sync_timestamps["tenant-1"] = time.time()  # recently synced

    with patch("src.web.routes.asyncio.create_task") as mock_create:
        _maybe_trigger_pd_sync("tenant-1")  # should skip
        _maybe_trigger_pd_sync("tenant-2")  # should trigger

    mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# _background_pd_sync — resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_returns_silently_when_no_token():
    """If no PD token is found, the sync should return without error."""
    mock_token_store = MagicMock()
    mock_token_store.get_token = AsyncMock(return_value=None)

    with (
        patch("src.web.routes.incident_store") as mock_store,
        patch(
            "src.integrations.oauth_tokens.oauth_token_store",
            mock_token_store,
        ),
    ):
        # Should not raise
        await _background_pd_sync("tenant-no-pd")

    # No incidents should have been added
    mock_store.add_incident.assert_not_called()


@pytest.mark.asyncio
async def test_sync_failure_does_not_raise():
    """If the PD API call fails, the sync catches the exception silently."""
    mock_token_store = MagicMock()
    mock_token_rec = MagicMock()
    mock_token_rec.access_token = "xoxb-fake"
    mock_token_store.get_token = AsyncMock(return_value=mock_token_rec)

    # Make httpx.AsyncClient.get raise
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("src.web.routes.incident_store") as mock_store,
        patch(
            "src.integrations.oauth_tokens.oauth_token_store",
            mock_token_store,
        ),
        patch("httpx.AsyncClient", return_value=mock_client_instance),
    ):
        # Should not raise even though API returned 500
        await _background_pd_sync("tenant-err")

    mock_store.add_incident.assert_not_called()


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
