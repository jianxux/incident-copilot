"""Onboarding checklist tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

CHECKLIST_STEPS = [
    "create_account",
    "connect_alerting",
    "connect_slack",
    "connect_github",
    "connect_datadog",
    "add_services",
    "run_test",
    "go_live",
]

# Optional steps don't count toward progress percentage
OPTIONAL_STEPS = {"connect_github", "connect_datadog"}


@dataclass
class OnboardingChecklist:
    tenant_id: str
    completed: dict[str, bool] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self):
        for step in CHECKLIST_STEPS:
            self.completed.setdefault(step, False)

    def mark(self, step: str, value: bool = True) -> None:
        if step not in CHECKLIST_STEPS:
            raise ValueError(f"Unknown onboarding step: {step}")
        self.completed[step] = value
        self.updated_at = datetime.now(UTC)

    @property
    def progress(self) -> float:
        required = [s for s in CHECKLIST_STEPS if s not in OPTIONAL_STEPS]
        total = len(required)
        done = sum(1 for s in required if self.completed.get(s))
        return done / total if total else 0.0

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "steps": [
                {
                    "id": s,
                    "title": _title(s),
                    "done": bool(self.completed.get(s)),
                    "optional": s in OPTIONAL_STEPS,
                }
                for s in CHECKLIST_STEPS
            ],
            "progress": self.progress,
            "updated_at": self.updated_at.isoformat(),
        }


def _title(step: str) -> str:
    titles = {
        "create_account": "Create account",
        "connect_alerting": "Connect alerting (PagerDuty/Opsgenie)",
        "connect_slack": "Connect Slack",
        "connect_github": "Connect GitHub (optional)",
        "connect_datadog": "Connect Datadog (optional)",
        "add_services": "Add services",
        "run_test": "Run a test incident",
        "go_live": "Go live",
    }
    return titles.get(step, step)
