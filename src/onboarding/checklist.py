"""Onboarding checklist tracking.

This module provides a persistent-ish (in-memory for now) checklist that tracks
onboarding progress for a tenant.

In production this should be stored in a DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()


CHECKLIST_STEPS = [
    "create_account",
    "connect_alerting",
    "connect_slack",
    "add_services",
    "run_test",
    "go_live",
]


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
        total = len(CHECKLIST_STEPS)
        done = sum(1 for s in CHECKLIST_STEPS if self.completed.get(s))
        return done / total if total else 0.0

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "steps": [
                {
                    "id": s,
                    "title": _title(s),
                    "done": bool(self.completed.get(s)),
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
        "add_services": "Add services",
        "run_test": "Run a test incident",
        "go_live": "Go live",
    }
    return titles.get(step, step)


class ChecklistStore:
    """In-memory checklist store."""

    def __init__(self):
        self._items: dict[str, OnboardingChecklist] = {}

    def get(self, tenant_id: str) -> OnboardingChecklist:
        if tenant_id not in self._items:
            self._items[tenant_id] = OnboardingChecklist(tenant_id=tenant_id)
        return self._items[tenant_id]

    def set_step(self, tenant_id: str, step: str, value: bool = True) -> OnboardingChecklist:
        checklist = self.get(tenant_id)
        checklist.mark(step, value)
        logger.info("onboarding_step_updated", tenant_id=tenant_id, step=step, value=value)
        return checklist


checklist_store = ChecklistStore()
