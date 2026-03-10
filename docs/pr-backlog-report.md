# PR Backlog Report

`scripts/pr_backlog_report.py` prints a lightweight backlog summary for open pull requests. It prefers live data from `gh api` whenever the repository can be resolved and falls back to a bundled JSON fixture if `gh` cannot fetch the repo.

## Usage

From the repo root:

```bash
python scripts/pr_backlog_report.py
```

Target a specific repository instead of inferring `origin`:

```bash
python scripts/pr_backlog_report.py --repo owner/repo
```

Use a custom fixture file:

```bash
python scripts/pr_backlog_report.py --fixture /tmp/open-prs.json
```

## Output

The report includes:

- Total open PR count
- Likely duplicate groups based on normalized title prefixes
- Fixed age buckets (`0-7d`, `8-30d`, `31-90d`, `91d+`)
- Top risky clusters with more than 3 similar PRs

Example:

```text
PR Backlog Report
Source: fixture (scripts/fixtures/pr_backlog_open_prs.json)
Total open PRs: 7

Likely duplicate groups:
- feat add incident export (4)
  #103 [api] feat add incident export filters to markdown (2026-02-18)
  #102 Draft: feat add incident export filters for csv (2026-03-01)
  #101 feat: add incident export filters (2026-03-09)

Age buckets:
- 0-7d: 2
- 8-30d: 2
- 31-90d: 2
- 91d+: 1

Top risky clusters (>3 similar PRs):
- feat add incident export: 4 PRs, oldest 2026-01-20, newest 2026-03-09
```
