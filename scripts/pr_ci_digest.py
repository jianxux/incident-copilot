#!/usr/bin/env python3
"""Summarize CI health across open pull requests using the GitHub CLI."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from typing import Any

PR_LIST_FIELDS = "number,title,url,author,headRefName,updatedAt"
PR_CHECK_FIELDS = "name,state,bucket,workflow,link"
CONVENTIONAL_PREFIXES = (
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "style",
    "test",
)
LEADING_MARKER_RE = re.compile(
    r"^(?:\[(?:draft|wip)\]|\((?:draft|wip)\)|draft:|wip:)\s*", re.IGNORECASE
)
PREFIX_RE = re.compile(
    rf"^(?:{'|'.join(CONVENTIONAL_PREFIXES)})(?:\([^)]+\))?!?:\s*",
    re.IGNORECASE,
)
SEPARATOR_RE = re.compile(r"[\s._/-]+")


def normalize_title(title: str) -> str:
    """Normalize titles to cluster likely duplicates."""
    normalized = title.strip()

    while True:
        updated = LEADING_MARKER_RE.sub("", normalized).strip()
        updated = PREFIX_RE.sub("", updated).strip()
        if updated == normalized:
            break
        normalized = updated

    normalized = normalized.casefold()
    normalized = re.sub(r"[^\w\s-]", " ", normalized)
    normalized = SEPARATOR_RE.sub(" ", normalized).strip()
    return normalized or title.strip().casefold()


def classify_overall_bucket(counts: Counter[str]) -> str:
    """Reduce check buckets down to an overall PR CI state."""
    if counts["fail"] or counts["cancel"]:
        return "fail"
    if counts["pending"]:
        return "pending"
    if counts["pass"]:
        return "pass"
    if counts["skipping"]:
        return "skipping"
    return "unknown"


def check_label(check: dict[str, Any]) -> str:
    """Build a stable label for a check run."""
    workflow = (check.get("workflow") or "").strip()
    name = (check.get("name") or "").strip() or "(unnamed)"
    if workflow and workflow != name:
        return f"{workflow} / {name}"
    return name


def summarize_pr(pr: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize CI status for a single pull request."""
    counts: Counter[str] = Counter()
    failing_checks: list[str] = []
    pending_checks: list[str] = []

    for check in checks:
        bucket = (check.get("bucket") or "").strip().lower()
        if not bucket:
            state = (check.get("state") or "").strip().lower()
            bucket = (
                "pending"
                if state in {"queued", "in_progress", "pending", "waiting"}
                else state
            )

        counts[bucket] += 1
        label = check_label(check)
        if bucket in {"fail", "cancel"}:
            failing_checks.append(label)
        elif bucket == "pending":
            pending_checks.append(label)

    title = str(pr["title"])
    return {
        "number": pr["number"],
        "title": title,
        "normalized_title": normalize_title(title),
        "url": pr["url"],
        "author": (pr.get("author") or {}).get("login"),
        "head_ref": pr.get("headRefName"),
        "updated_at": pr.get("updatedAt"),
        "check_counts": {bucket: counts[bucket] for bucket in sorted(counts)},
        "overall_bucket": classify_overall_bucket(counts),
        "failing_checks": sorted(failing_checks),
        "pending_checks": sorted(pending_checks),
        "total_checks": sum(counts.values()),
    }


def aggregate_prs(
    prs: list[dict[str, Any]], checks_by_pr: dict[int, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Aggregate PR summaries, failing check frequency, and duplicate titles."""
    pr_summaries: list[dict[str, Any]] = []
    failing_frequency: Counter[str] = Counter()
    duplicate_clusters: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    overall_counts: Counter[str] = Counter()

    for pr in prs:
        number = int(pr["number"])
        summary = summarize_pr(pr, checks_by_pr.get(number, []))
        pr_summaries.append(summary)
        overall_counts[summary["overall_bucket"]] += 1
        duplicate_clusters[summary["normalized_title"]].append(
            {
                "number": summary["number"],
                "title": summary["title"],
                "url": summary["url"],
            }
        )
        for check_name in summary["failing_checks"]:
            failing_frequency[check_name] += 1

    duplicate_title_clusters = [
        {
            "normalized_title": title,
            "count": len(cluster),
            "pull_requests": sorted(cluster, key=lambda pr: pr["number"]),
        }
        for title, cluster in duplicate_clusters.items()
        if len(cluster) > 1
    ]
    duplicate_title_clusters.sort(
        key=lambda cluster: (-cluster["count"], cluster["normalized_title"])
    )

    pr_summaries.sort(key=lambda pr: pr["number"], reverse=True)
    failing_checks = [
        {"name": name, "count": count}
        for name, count in sorted(
            failing_frequency.items(), key=lambda item: (-item[1], item[0])
        )
    ]

    return {
        "summary": {
            "total_open_prs": len(pr_summaries),
            "overall_buckets": {
                bucket: overall_counts[bucket] for bucket in sorted(overall_counts)
            },
            "prs_with_failures": sum(1 for pr in pr_summaries if pr["failing_checks"]),
            "prs_with_pending": sum(1 for pr in pr_summaries if pr["pending_checks"]),
        },
        "pull_requests": pr_summaries,
        "failing_check_frequency": failing_checks,
        "duplicate_title_clusters": duplicate_title_clusters,
    }


def gh_json(args: list[str]) -> Any:
    """Run a gh command that emits JSON and decode the result."""
    result = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown gh error"
        raise RuntimeError(f"gh {' '.join(args)} failed: {stderr}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh {' '.join(args)} returned invalid JSON") from exc


def fetch_open_prs(limit: int, repo: str | None) -> list[dict[str, Any]]:
    """Fetch open pull requests using gh CLI JSON output."""
    args = [
        "pr",
        "list",
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        PR_LIST_FIELDS,
    ]
    if repo:
        args.extend(["--repo", repo])
    return gh_json(args)


def fetch_pr_checks(
    number: int, repo: str | None, required_only: bool
) -> list[dict[str, Any]]:
    """Fetch CI checks for a pull request using gh CLI JSON output."""
    args = ["pr", "checks", str(number), "--json", PR_CHECK_FIELDS]
    if required_only:
        args.append("--required")
    if repo:
        args.extend(["--repo", repo])
    return gh_json(args)


def render_text(digest: dict[str, Any]) -> str:
    """Render the digest in a compact text format."""
    summary = digest["summary"]
    lines = [
        f"Open PR CI digest: {summary['total_open_prs']} PRs",
        f"Overall buckets: {summary['overall_buckets']}",
        "",
        "Per-PR status:",
    ]

    for pr in digest["pull_requests"]:
        lines.append(
            f"- #{pr['number']} [{pr['overall_bucket']}] {pr['title']} "
            f"(fail={len(pr['failing_checks'])}, pending={len(pr['pending_checks'])}, total={pr['total_checks']})"
        )
        if pr["failing_checks"]:
            lines.append(f"  failing: {', '.join(pr['failing_checks'])}")
        if pr["pending_checks"]:
            lines.append(f"  pending: {', '.join(pr['pending_checks'])}")

    lines.append("")
    lines.append("Failing check frequency:")
    if digest["failing_check_frequency"]:
        for item in digest["failing_check_frequency"]:
            lines.append(f"- {item['name']}: {item['count']}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Duplicate title clusters:")
    if digest["duplicate_title_clusters"]:
        for cluster in digest["duplicate_title_clusters"]:
            refs = ", ".join(f"#{pr['number']}" for pr in cluster["pull_requests"])
            lines.append(
                f"- {cluster['normalized_title']}: {cluster['count']} PRs ({refs})"
            )
    else:
        lines.append("- none")

    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=30, help="Maximum number of open PRs to inspect"
    )
    parser.add_argument("--repo", help="Optional [HOST/]OWNER/REPO override for gh")
    parser.add_argument(
        "--required",
        action="store_true",
        help="Only include required checks when summarizing CI status",
    )
    parser.add_argument("--json", action="store_true", help="Emit the digest as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit <= 0:
        print("--limit must be greater than 0", file=sys.stderr)
        return 2

    try:
        prs = fetch_open_prs(args.limit, args.repo)
        checks_by_pr = {
            int(pr["number"]): fetch_pr_checks(
                int(pr["number"]), args.repo, args.required
            )
            for pr in prs
        }
        digest = aggregate_prs(prs, checks_by_pr)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(digest, indent=2))
    else:
        print(render_text(digest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
