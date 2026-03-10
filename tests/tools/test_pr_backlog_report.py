from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "pr_backlog_report.py"
SPEC = importlib.util.spec_from_file_location("pr_backlog_report", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def build_pr(number: int, title: str, created_at: str) -> object:
    return MODULE.PullRequest(
        number=number,
        title=title,
        created_at=MODULE.parse_github_datetime(created_at),
        html_url=f"https://example.com/pr/{number}",
    )


def test_normalize_title_prefix_strips_noise_and_limits_prefix():
    normalized = MODULE.normalize_title_prefix(
        "Draft: [api] Fix auth refresh race on token rotation!!!"
    )

    assert normalized == "fix auth refresh race"


def test_group_prs_by_prefix_keeps_only_duplicate_clusters():
    pull_requests = [
        build_pr(1, "feat add incident export filters", "2026-03-09T00:00:00Z"),
        build_pr(2, "Draft: feat add incident export filters for csv", "2026-03-01T00:00:00Z"),
        build_pr(3, "[api] feat add incident export filters to markdown", "2026-02-18T00:00:00Z"),
        build_pr(4, "fix auth refresh race", "2026-03-08T00:00:00Z"),
    ]

    groups = MODULE.group_prs_by_prefix(pull_requests)

    assert list(groups) == ["feat add incident export"]
    assert [item.number for item in groups["feat add incident export"]] == [3, 2, 1]


def test_build_age_buckets_counts_expected_ranges():
    now = datetime(2026, 3, 10, tzinfo=UTC)
    pull_requests = [
        build_pr(1, "one", "2026-03-09T00:00:00Z"),
        build_pr(2, "two", "2026-03-01T00:00:00Z"),
        build_pr(3, "three", "2026-02-01T00:00:00Z"),
        build_pr(4, "four", "2025-11-01T00:00:00Z"),
    ]

    buckets = MODULE.build_age_buckets(pull_requests, now=now)

    assert buckets == {
        "0-7d": 1,
        "8-30d": 1,
        "31-90d": 1,
        "91d+": 1,
    }


def test_resolve_pull_requests_tries_gh_without_token(monkeypatch, tmp_path):
    fixture_path = tmp_path / "open-prs.json"
    fixture_path.write_text("[]")
    calls: list[str] = []

    def fake_fetch(repo: str) -> list[object]:
        calls.append(repo)
        return [build_pr(1, "feat add incident export filters", "2026-03-09T00:00:00Z")]

    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(MODULE, "fetch_open_prs_via_gh", fake_fetch)

    pull_requests, source = MODULE.resolve_pull_requests("owner/repo", fixture_path)

    assert calls == ["owner/repo"]
    assert [item.number for item in pull_requests] == [1]
    assert source == "gh api (owner/repo)"


def test_resolve_pull_requests_falls_back_to_fixture_after_fetch_failure(
    monkeypatch, tmp_path
):
    fixture_path = tmp_path / "open-prs.json"
    fixture_path.write_text(
        '[{"number": 7, "title": "fixture pr", "created_at": "2026-03-01T00:00:00Z", "html_url": "https://example.com/pr/7"}]'
    )

    def fake_fetch(repo: str) -> list[object]:
        raise subprocess.CalledProcessError(returncode=1, cmd=["gh", "api", repo])

    monkeypatch.setattr(MODULE, "fetch_open_prs_via_gh", fake_fetch)

    pull_requests, source = MODULE.resolve_pull_requests("owner/repo", fixture_path)

    assert [item.number for item in pull_requests] == [7]
    assert source == f"fixture ({fixture_path})"
