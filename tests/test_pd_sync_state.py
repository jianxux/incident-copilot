from datetime import datetime, timedelta, timezone

import pytest

from src.api.incidents import _derive_pd_sync_state


@pytest.mark.parametrize(
    ("status_data", "expected"),
    [
        ({"in_progress": True}, "syncing"),
        (
            {
                "last_attempt": datetime.now(timezone.utc).isoformat(),
                "last_error": "sync failed",
            },
            "error",
        ),
        (
            {
                "last_attempt": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
                "last_success": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
            },
            "synced",
        ),
        ({}, "never"),
    ],
)
def test_derive_pd_sync_state_matches_frontend_expected_values(status_data, expected):
    result = _derive_pd_sync_state(status_data)

    assert result == expected
    assert result in {"synced", "syncing", "error", "never"}
