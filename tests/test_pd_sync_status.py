from datetime import UTC, datetime, timedelta

from src.api.incidents import _derive_pd_sync_state


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def test_returns_syncing_when_in_progress_true():
    status = _derive_pd_sync_state({"in_progress": True})
    assert status == "syncing"


def test_returns_never_when_no_attempt():
    status = _derive_pd_sync_state({})
    assert status == "never"


def test_returns_error_when_last_error_exists_and_no_success_after():
    now = datetime.now(UTC)
    status = _derive_pd_sync_state(
        {
            "last_attempt": _iso(now),
            "last_success": _iso(now - timedelta(minutes=5)),
            "last_error": "token expired",
        }
    )
    assert status == "error"


def test_returns_synced_when_success_is_old_stale_window():
    now = datetime.now(UTC)
    status = _derive_pd_sync_state(
        {
            "last_attempt": _iso(now - timedelta(seconds=601)),
            "last_success": _iso(now - timedelta(seconds=601)),
        }
    )
    assert status == "synced"


def test_returns_synced_when_recently_successful():
    now = datetime.now(UTC)
    status = _derive_pd_sync_state(
        {
            "last_attempt": _iso(now - timedelta(seconds=120)),
            "last_success": _iso(now - timedelta(seconds=120)),
        }
    )
    assert status == "synced"
