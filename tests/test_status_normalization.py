"""Tests for status normalization (_map_status) and status_color."""

from src.web.routes import _map_status, status_color


class TestMapStatus:
    """Tests for _map_status normalization."""

    def test_processing_maps_to_triggered(self):
        assert _map_status("processing") == "triggered"

    def test_completed_maps_to_resolved(self):
        assert _map_status("completed") == "resolved"

    def test_error_maps_to_triggered(self):
        assert _map_status("error") == "triggered"

    def test_triggered_passes_through(self):
        assert _map_status("triggered") == "triggered"

    def test_acknowledged_passes_through(self):
        assert _map_status("acknowledged") == "acknowledged"

    def test_resolved_passes_through(self):
        assert _map_status("resolved") == "resolved"

    def test_none_defaults_to_triggered(self):
        assert _map_status(None) == "triggered"

    def test_case_insensitive(self):
        assert _map_status("Processing") == "triggered"
        assert _map_status("COMPLETED") == "resolved"

    def test_whitespace_stripped(self):
        assert _map_status("  processing  ") == "triggered"

    def test_unknown_passes_through_lowered(self):
        assert _map_status("CustomStatus") == "customstatus"


class TestStatusColor:
    """Tests for status_color Tailwind class mapping."""

    def test_lifecycle_statuses(self):
        assert status_color("triggered") == "bg-yellow-500"
        assert status_color("acknowledged") == "bg-blue-500"
        assert status_color("resolved") == "bg-green-500"
        assert status_color("error") == "bg-red-500"

    def test_legacy_statuses(self):
        assert status_color("processing") == "bg-yellow-500"
        assert status_color("completed") == "bg-green-500"

    def test_unknown_returns_gray(self):
        assert status_color("unknown") == "bg-gray-500"

    def test_none_returns_gray(self):
        assert status_color(None) == "bg-gray-500"

    def test_case_insensitive(self):
        assert status_color("Triggered") == "bg-yellow-500"
        assert status_color("RESOLVED") == "bg-green-500"
