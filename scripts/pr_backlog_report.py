#!/usr/bin/env python3
"""Report backlog patterns for open pull requests."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FIXTURE_PATH = Path(__file__).with_name("fixtures") / "pr_backlog_open_prs.json"
TITLE_PREFIX_PATTERN = re.compile(r"^(?:draft|wip)\s*[:\-]\s*", re.IGNORECASE)
BRACKET_PREFIX_PATTERN = re.compile(r"^(?:\[[^\]]+\]\s*)+")
PUNCTUATION_PATTERN = re.compile(r"[^a-z0-9]+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}
AGE_BUCKETS = (
    ("0-7d", 0, 7),
    ("8-30d", 8, 30),
    ("31-90d", 31, 90),
    ("91d+", 91, None),
)
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


@dataclass
class PullRequest:
    """Minimal pull request metadata used by the report."""

    number: int
    title: str
    created_at: datetime
    html_url: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> PullRequest:
        return cls(
            number=int(payload["number"]),
            title=str(payload["title"]),
            created_at=parse_github_datetime(str(payload["created_at"])),
            html_url=str(payload.get("html_url", "")),
        )


def parse_github_datetime(value: str) -> datetime:
    """Parse a GitHub API timestamp into an aware UTC datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def infer_repo_from_git(cwd: Path | None = None) -> str | None:
    """Infer owner/repo from git remote origin."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd,
            capture_output=True,
            check=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    remote = result.stdout.strip()
    ssh_match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", remote)
    return ssh_match.group(1) if ssh_match else None


def normalize_title_prefix(title: str, *, max_tokens: int = 4) -> str:
    """Normalize a PR title into a coarse duplicate-detection prefix."""
    cleaned = title.strip().lower()
    cleaned = TITLE_PREFIX_PATTERN.sub("", cleaned)
    cleaned = BRACKET_PREFIX_PATTERN.sub("", cleaned)
    tokens = [
        token
        for token in PUNCTUATION_PATTERN.sub(" ", cleaned).split()
        if token and token not in STOP_WORDS and not token.isdigit()
    ]
    return " ".join(tokens[:max_tokens])


def group_prs_by_prefix(
    pull_requests: list[PullRequest],
    *,
    min_group_size: int = 2,
) -> dict[str, list[PullRequest]]:
    """Group PRs by normalized title prefix."""
    grouped: dict[str, list[PullRequest]] = defaultdict(list)
    for pull_request in pull_requests:
        prefix = normalize_title_prefix(pull_request.title)
        if prefix:
            grouped[prefix].append(pull_request)

    return {
        prefix: sorted(group, key=lambda item: item.created_at)
        for prefix, group in grouped.items()
        if len(group) >= min_group_size
    }


def build_age_buckets(
    pull_requests: list[PullRequest],
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Count open PRs into fixed age buckets."""
    current = now or datetime.now(UTC)
    counts = Counter({label: 0 for label, _, _ in AGE_BUCKETS})
    for pull_request in pull_requests:
        age_days = max(0, (current - pull_request.created_at).days)
        for label, minimum, maximum in AGE_BUCKETS:
            if age_days < minimum:
                continue
            if maximum is None or age_days <= maximum:
                counts[label] += 1
                break
    return {label: counts[label] for label, _, _ in AGE_BUCKETS}


def load_fixture_data(path: Path = FIXTURE_PATH) -> list[PullRequest]:
    """Load mock PR data from disk."""
    payload = json.loads(path.read_text())
    return [PullRequest.from_api(item) for item in payload]


def fetch_open_prs_via_gh(repo: str) -> list[PullRequest]:
    """Fetch open PRs from the GitHub CLI."""
    command = [
        "gh",
        "api",
        f"repos/{repo}/pulls",
        "--paginate",
        "--field",
        "state=open",
        "--field",
        "per_page=100",
    ]
    result = subprocess.run(command, capture_output=True, check=True, text=True)
    payload = json.loads(result.stdout)
    return [PullRequest.from_api(item) for item in payload]


def resolve_pull_requests(
    repo: str | None, fixture_path: Path = FIXTURE_PATH
) -> tuple[list[PullRequest], str]:
    """Load PRs from GitHub when possible, otherwise use the fixture."""
    resolved_repo = repo or infer_repo_from_git(Path.cwd())
    if resolved_repo:
        try:
            return fetch_open_prs_via_gh(resolved_repo), f"gh api ({resolved_repo})"
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError):
            pass
    return load_fixture_data(fixture_path), f"fixture ({fixture_path})"


def render_report(
    pull_requests: list[PullRequest],
    *,
    source: str,
    now: datetime | None = None,
) -> str:
    """Render the backlog report as plain text."""
    groups = group_prs_by_prefix(pull_requests)
    age_buckets = build_age_buckets(pull_requests, now=now)
    risky_clusters = sorted(
        ((prefix, group) for prefix, group in groups.items() if len(group) > 3),
        key=lambda item: (-len(item[1]), item[1][0].created_at),
    )

    lines = [
        "PR Backlog Report",
        f"Source: {source}",
        f"Total open PRs: {len(pull_requests)}",
        "",
        "Likely duplicate groups:",
    ]

    if groups:
        for prefix, group in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
            lines.append(f"- {prefix} ({len(group)})")
            for pull_request in group[:5]:
                lines.append(
                    f"  #{pull_request.number} {pull_request.title} "
                    f"({pull_request.created_at.date().isoformat()})"
                )
    else:
        lines.append("- none")

    lines.extend(["", "Age buckets:"])
    for label, count in age_buckets.items():
        lines.append(f"- {label}: {count}")

    lines.extend(["", "Top risky clusters (>3 similar PRs):"])
    if risky_clusters:
        for prefix, group in risky_clusters[:5]:
            oldest = group[0].created_at.date().isoformat()
            newest = group[-1].created_at.date().isoformat()
            lines.append(f"- {prefix}: {len(group)} PRs, oldest {oldest}, newest {newest}")
    else:
        lines.append("- none")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", help="GitHub repo in owner/name form. Default: infer from git remote."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=FIXTURE_PATH,
        help="Fixture path to use when gh access is unavailable.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args(argv)
    pull_requests, source = resolve_pull_requests(args.repo, args.fixture)
    print(render_report(pull_requests, source=source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
