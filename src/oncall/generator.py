"""Handoff summary generator.

Uses Claude (Anthropic) when configured; otherwise falls back to a deterministic
heuristic formatter.
"""

from __future__ import annotations

import json
from datetime import datetime

import structlog
from anthropic import AsyncAnthropic

from ..config import Settings
from .models import HandoffAggregate, HandoffSummary

logger = structlog.get_logger()

_HANDOFF_PROMPT = """You are an expert SRE writing an on-call handoff note.

Write a concise, actionable handoff brief in Markdown that can be read in 30 seconds.

Shift window (UTC): {shift_start} to {shift_end}
Outgoing: {outgoing}
Incoming: {incoming}

Data (JSON):
{data_json}

Instructions:
- Output MUST be Markdown.
- Use EXACTLY these sections in this order:
  1) Active Issues
  2) Resolved This Shift
  3) Watch Items
  4) Key Metrics
- Prioritize by severity/urgency. P1/P2 (or high urgency) get 2-4 bullets each.
- For each active issue: include a one-line status + 1-3 "Next step" bullets.
- Keep the whole brief under ~2500 characters.
- If a section has no items, write "(none)".

Return ONLY the Markdown, no backticks, no extra commentary.
"""


class HandoffSummaryGenerator:
    """Generate a handoff summary from aggregated shift data."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            AsyncAnthropic(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )
        self.model = settings.ai_model

    async def generate(self, aggregate: HandoffAggregate) -> HandoffSummary:
        """Generate a handoff summary."""
        title = self._default_title(aggregate)

        if not self.client:
            brief = self._heuristic_markdown(aggregate)
            return HandoffSummary(
                id=self._new_id(),
                shift=aggregate.shift,
                aggregate=aggregate,
                title=title,
                brief_markdown=brief,
                generator="heuristic",
                model=None,
            )

        try:
            prompt = _HANDOFF_PROMPT.format(
                shift_start=aggregate.shift.shift_start.isoformat(),
                shift_end=aggregate.shift.shift_end.isoformat(),
                outgoing=(
                    aggregate.shift.outgoing.name
                    if aggregate.shift.outgoing
                    else "unknown"
                ),
                incoming=(
                    aggregate.shift.incoming.name
                    if aggregate.shift.incoming
                    else "unknown"
                ),
                data_json=json.dumps(
                    aggregate.model_dump(mode="json"), ensure_ascii=False
                )[:12000],
            )

            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=900,
                messages=[{"role": "user", "content": prompt}],
            )

            content = "".join(
                getattr(block, "text", "") for block in resp.content
            ).strip()
            if not content:
                raise ValueError("empty model response")

            return HandoffSummary(
                id=self._new_id(),
                shift=aggregate.shift,
                aggregate=aggregate,
                title=title,
                brief_markdown=content,
                generator="claude",
                model=self.model,
            )

        except Exception as e:
            logger.warning("handoff_ai_generation_failed", error=str(e))
            brief = self._heuristic_markdown(aggregate)
            return HandoffSummary(
                id=self._new_id(),
                shift=aggregate.shift,
                aggregate=aggregate,
                title=title,
                brief_markdown=brief,
                generator="heuristic_fallback",
                model=None,
            )

    def _heuristic_markdown(self, aggregate: HandoffAggregate) -> str:
        s = aggregate.shift
        lines: list[str] = []
        lines.append(
            f"# On-Call Handoff ({s.shift_start:%Y-%m-%d %H:%M}–{s.shift_end:%H:%M} UTC)"
        )

        # Active
        lines.append("\n## Active Issues")
        if not aggregate.active_incidents:
            lines.append("(none)")
        else:
            for inc in aggregate.active_incidents[:12]:
                sev = inc.severity or ""
                svc = f" — {inc.service}" if inc.service else ""
                url = f" ({inc.url})" if inc.url else ""
                status = f"[{inc.status}] " if inc.status else ""
                lines.append(f"- {status}{inc.title}{svc} {sev}{url}".strip())
                if inc.summary:
                    lines.append(f"  - Summary: {inc.summary}")
                if inc.next_steps:
                    for step in inc.next_steps[:3]:
                        lines.append(f"  - Next step: {step}")

        # Resolved
        lines.append("\n## Resolved This Shift")
        if not aggregate.resolved_incidents:
            lines.append("(none)")
        else:
            for inc in aggregate.resolved_incidents[:12]:
                svc = f" — {inc.service}" if inc.service else ""
                url = f" ({inc.url})" if inc.url else ""
                lines.append(f"- {inc.title}{svc}{url}")

        # Watch
        lines.append("\n## Watch Items")
        if not aggregate.watch_items:
            lines.append("(none)")
        else:
            for w in aggregate.watch_items[:10]:
                lines.append(f"- {w}")

        # Metrics
        m = aggregate.metrics
        lines.append("\n## Key Metrics")
        lines.append(f"- Incidents opened: {m.incidents_opened}")
        lines.append(f"- Incidents resolved: {m.incidents_resolved}")
        lines.append(f"- Incidents escalated: {m.incidents_escalated}")
        lines.append(
            f"- Acknowledged but unresolved: {m.alerts_acknowledged_unresolved}"
        )

        return "\n".join(lines).strip()[:2800]

    def _default_title(self, aggregate: HandoffAggregate) -> str:
        s = aggregate.shift
        start = s.shift_start.strftime("%Y-%m-%d")
        outgoing = s.outgoing.name if s.outgoing else "Outgoing"
        incoming = s.incoming.name if s.incoming else "Incoming"
        return f"On-Call Handoff — {start} — {outgoing} → {incoming}"

    def _new_id(self) -> str:
        return datetime.utcnow().strftime("handoff_%Y%m%d_%H%M%S_") + self._rand()

    def _rand(self) -> str:
        import secrets

        return secrets.token_hex(4)
