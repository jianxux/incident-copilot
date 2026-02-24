"""Handoff summary generator.

Uses Claude (Anthropic) when configured; otherwise falls back to a deterministic
heuristic formatter.
"""

from __future__ import annotations

import json
from datetime import datetime, UTC

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

_CATCHUP_PROMPT = """You are an SRE assistant writing a concise catch-up note.

Someone is joining mid-shift and needs the latest signal quickly.

Data (JSON):
{data_json}

Instructions:
- Output Markdown only.
- Keep it under ~1200 characters.
- Use exactly these sections:
  1) Current Critical Context
  2) Last {since_message_count} Key Events
  3) Immediate Next Actions
- Focus on active/high-severity items.
- If a section has no entries, write "(none)".
"""

_TITLE_PROMPT = """Generate a concise incident handoff title (max 80 chars).

Use this JSON data:
{data_json}

Rules:
- Output title text only, no punctuation decoration.
- Include primary service/impact if obvious.
- Keep it actionable.
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
        title = await self.generate_title(aggregate)

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

    async def generate_catchup(
        self,
        aggregate: HandoffAggregate,
        since_message_count: int,
    ) -> HandoffSummary:
        """Generate a short catch-up summary for mid-shift joiners."""
        title = await self.generate_title(aggregate)

        if not self.client:
            brief = self._heuristic_catchup_markdown(aggregate, since_message_count)
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
            prompt = _CATCHUP_PROMPT.format(
                since_message_count=max(1, since_message_count),
                data_json=json.dumps(
                    aggregate.model_dump(mode="json"), ensure_ascii=False
                )[:8000],
            )

            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=500,
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
            logger.warning("handoff_catchup_generation_failed", error=str(e))
            brief = self._heuristic_catchup_markdown(aggregate, since_message_count)
            return HandoffSummary(
                id=self._new_id(),
                shift=aggregate.shift,
                aggregate=aggregate,
                title=title,
                brief_markdown=brief,
                generator="heuristic_fallback",
                model=None,
            )

    async def generate_title(self, aggregate: HandoffAggregate) -> str:
        """Generate a concise incident title, using AI when available."""
        fallback = self._default_title(aggregate)
        if not self.client:
            return fallback

        try:
            prompt = _TITLE_PROMPT.format(
                data_json=json.dumps(
                    {
                        "shift": aggregate.shift.model_dump(mode="json"),
                        "active_incidents": [
                            i.model_dump(mode="json")
                            for i in aggregate.active_incidents[:5]
                        ],
                        "watch_items": aggregate.watch_items[:5],
                        "metrics": aggregate.metrics.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                )[:4000]
            )
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=64,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(getattr(block, "text", "") for block in resp.content)
            clean = " ".join(text.split()).strip()
            if not clean:
                return fallback
            return clean[:80]
        except Exception as e:
            logger.warning("handoff_title_generation_failed", error=str(e))
            return fallback

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

    def _heuristic_catchup_markdown(
        self,
        aggregate: HandoffAggregate,
        since_message_count: int,
    ) -> str:
        lines: list[str] = []
        lines.append("## Current Critical Context")
        active = aggregate.active_incidents[: max(1, since_message_count)]
        if not active:
            lines.append("(none)")
        else:
            for inc in active[:5]:
                sev = f"[{inc.severity}] " if inc.severity else ""
                status = f"({inc.status})" if inc.status else ""
                lines.append(f"- {sev}{inc.title} {status}".strip())

        lines.append(f"\n## Last {max(1, since_message_count)} Key Events")
        events = (aggregate.active_incidents + aggregate.resolved_incidents)[
            : max(1, since_message_count)
        ]
        if not events:
            lines.append("(none)")
        else:
            for event in events:
                lines.append(f"- {event.title}")

        lines.append("\n## Immediate Next Actions")
        next_steps: list[str] = []
        for inc in aggregate.active_incidents[:5]:
            next_steps.extend(inc.next_steps)
        if aggregate.watch_items:
            next_steps.extend(aggregate.watch_items)

        if not next_steps:
            lines.append("(none)")
        else:
            for step in next_steps[:6]:
                lines.append(f"- {step}")

        return "\n".join(lines).strip()[:1500]

    def _new_id(self) -> str:
        return datetime.now(UTC).strftime("handoff_%Y%m%d_%H%M%S_") + self._rand()

    def _rand(self) -> str:
        import secrets

        return secrets.token_hex(4)
