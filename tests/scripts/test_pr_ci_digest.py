from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "pr_ci_digest.py"
    spec = importlib.util.spec_from_file_location("pr_ci_digest", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


pr_ci_digest = load_module()


def test_normalize_title_strips_common_prefixes_and_markers():
    assert pr_ci_digest.normalize_title("fix: API login timeout") == "api login timeout"
    assert (
        pr_ci_digest.normalize_title("Chore(auth): API login timeout")
        == "api login timeout"
    )
    assert (
        pr_ci_digest.normalize_title("[WIP] feat(ui): API login timeout")
        == "api login timeout"
    )


def test_aggregate_prs_reports_failures_pending_and_duplicate_clusters():
    prs = [
        {
            "number": 101,
            "title": "fix: API login timeout",
            "url": "https://example.test/101",
            "author": {"login": "alice"},
            "headRefName": "fix/login-timeout",
            "updatedAt": "2026-03-12T10:00:00Z",
        },
        {
            "number": 102,
            "title": "chore(auth): API login timeout",
            "url": "https://example.test/102",
            "author": {"login": "bob"},
            "headRefName": "chore/login-timeout",
            "updatedAt": "2026-03-12T11:00:00Z",
        },
        {
            "number": 103,
            "title": "feat: Add timeline export",
            "url": "https://example.test/103",
            "author": {"login": "carol"},
            "headRefName": "feat/timeline-export",
            "updatedAt": "2026-03-12T12:00:00Z",
        },
    ]
    checks_by_pr = {
        101: [
            {"name": "lint", "workflow": "CI", "bucket": "fail", "state": "FAILURE"},
            {"name": "unit", "workflow": "CI", "bucket": "pass", "state": "SUCCESS"},
        ],
        102: [
            {"name": "lint", "workflow": "CI", "bucket": "fail", "state": "FAILURE"},
            {
                "name": "integration",
                "workflow": "CI",
                "bucket": "pending",
                "state": "IN_PROGRESS",
            },
        ],
        103: [
            {"name": "unit", "workflow": "CI", "bucket": "pass", "state": "SUCCESS"},
        ],
    }

    digest = pr_ci_digest.aggregate_prs(prs, checks_by_pr)

    assert digest["summary"] == {
        "total_open_prs": 3,
        "overall_buckets": {"fail": 2, "pass": 1},
        "prs_with_failures": 2,
        "prs_with_pending": 1,
    }

    assert digest["failing_check_frequency"] == [{"name": "CI / lint", "count": 2}]
    assert digest["duplicate_title_clusters"] == [
        {
            "normalized_title": "api login timeout",
            "count": 2,
            "pull_requests": [
                {
                    "number": 101,
                    "title": "fix: API login timeout",
                    "url": "https://example.test/101",
                },
                {
                    "number": 102,
                    "title": "chore(auth): API login timeout",
                    "url": "https://example.test/102",
                },
            ],
        }
    ]

    by_number = {pr["number"]: pr for pr in digest["pull_requests"]}
    assert by_number[101]["overall_bucket"] == "fail"
    assert by_number[101]["failing_checks"] == ["CI / lint"]
    assert by_number[102]["pending_checks"] == ["CI / integration"]
    assert by_number[103]["overall_bucket"] == "pass"
