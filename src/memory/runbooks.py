"""Auto-generated runbooks from incident memory patterns."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from hashlib import sha1

import structlog
from anthropic import AsyncAnthropic

from ..config import Settings
from .config import IncidentMemoryConfig
from .models import GeneratedRunbook
from .store import IncidentMemoryStore

logger = structlog.get_logger()

RUNBOOK_SYNTHESIS_PROMPT = """You are generating an SRE runbook from recurring incident data.
Given the grouped incidents, synthesize a concise and practical runbook.
Return ONLY JSON with this schema:
{
  "title": "string",
  "trigger_conditions": ["string"],
  "steps": ["string"]
}

Group data:
{group_json}
"""


class AutoRunbookGenerator:
    """Analyze recurring incidents and persist generated runbooks."""

    def __init__(
        self,
        settings: Settings,
        store: IncidentMemoryStore,
        config: IncidentMemoryConfig,
        anthropic_client: AsyncAnthropic | None = None,
    ):
        self.settings = settings
        self.store = store
        self.config = config
        self._anthropic_client = anthropic_client or (
            AsyncAnthropic(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )

    async def rebuild(self) -> int:
        """Rebuild generated runbooks from incident memory."""
        groups = await self._collect_groups()
        runbooks: list[GeneratedRunbook] = []

        for group in groups[: self.config.runbook_max_groups]:
            runbook = await self._generate_for_group(group)
            if runbook is not None:
                runbooks.append(runbook)

        await self._replace_runbooks(runbooks)
        logger.info("memory_generated_runbooks_rebuilt", total=len(runbooks))
        return len(runbooks)

    async def list_runbooks(self, limit: int = 50) -> list[GeneratedRunbook]:
        pool = await self.store._ensure_pool()
        rows = await pool.fetch(
            f"""  # nosec B608
            SELECT *
            FROM {self.config.runbooks_table_name}
            ORDER BY confidence DESC, last_updated DESC
            LIMIT $1
            """,
            limit,
        )
        return [_row_to_runbook(row) for row in rows]

    async def get_runbook(self, runbook_id: str) -> GeneratedRunbook | None:
        pool = await self.store._ensure_pool()
        row = await pool.fetchrow(
            f"SELECT * FROM {self.config.runbooks_table_name} WHERE id = $1",  # nosec B608
            runbook_id,
        )
        if row is None:
            return None
        return _row_to_runbook(row)

    async def _collect_groups(self) -> list[dict[str, object]]:
        pool = await self.store._ensure_pool()
        rows = await pool.fetch(
            f"""  # nosec B608
            SELECT
                id,
                root_cause_category,
                services_affected,
                resolution_steps,
                resolution_summary
            FROM {self.config.table_name}
            WHERE array_length(services_affected, 1) > 0
              AND array_length(resolution_steps, 1) > 0
            """
        )

        grouped: dict[tuple[str, tuple[str, ...]], list[dict[str, object]]] = (
            defaultdict(list)
        )
        for row in rows:
            category = (
                str(row.get("root_cause_category") or "unknown").strip() or "unknown"
            )
            services_raw = row.get("services_affected")
            services = tuple(
                sorted(
                    str(item).strip()
                    for item in services_raw or []
                    if str(item).strip()
                )
            )
            if not services:
                continue
            grouped[(category, services)].append(
                {
                    "id": str(row["id"]),
                    "steps": [
                        str(item)
                        for item in (row.get("resolution_steps") or [])
                        if str(item).strip()
                    ],
                    "summary": str(row.get("resolution_summary") or "").strip(),
                }
            )

        groups: list[dict[str, object]] = []
        for (category, services), incidents in grouped.items():
            if len(incidents) < self.config.runbook_min_occurrences:
                continue
            groups.append(
                {
                    "root_cause_category": category,
                    "services_affected": list(services),
                    "incidents": incidents,
                }
            )

        groups.sort(key=lambda item: len(item["incidents"]), reverse=True)  # type: ignore[arg-type]
        return groups

    async def _generate_for_group(
        self,
        group: dict[str, object],
    ) -> GeneratedRunbook | None:
        incidents = group["incidents"]
        if not isinstance(incidents, list) or not incidents:
            return None

        source_ids = [
            str(item.get("id")) for item in incidents if isinstance(item, dict)
        ]
        services = [str(item) for item in group.get("services_affected", [])]  # type: ignore[arg-type]
        category = str(group.get("root_cause_category") or "unknown")
        steps = _fallback_steps(incidents)
        trigger_conditions = [
            f"root_cause_category={category}",
            f"services={', '.join(services)}",
        ]
        title = f"{category.title()} - {', '.join(services)}"

        synthesized = await self._synthesize_with_claude(group)
        if synthesized is not None:
            title = str(synthesized.get("title") or title)
            trigger_conditions = [
                str(item)
                for item in synthesized.get("trigger_conditions", [])
                if str(item).strip()
            ] or trigger_conditions
            steps = [
                str(item) for item in synthesized.get("steps", []) if str(item).strip()
            ] or steps

        confidence = min(1.0, round(len(source_ids) / (len(source_ids) + 2), 4))
        runbook_id = sha1(
            (f"{category}|{','.join(services)}|{','.join(sorted(source_ids))}").encode(
                "utf-8"
            )
        ).hexdigest()[:16]

        return GeneratedRunbook(
            id=runbook_id,
            title=title,
            trigger_conditions=trigger_conditions,
            steps=steps,
            source_incident_ids=source_ids,
            confidence=confidence,
            root_cause_category=category,
            services_affected=services,
            last_updated=datetime.now(UTC),
        )

    async def _synthesize_with_claude(
        self,
        group: dict[str, object],
    ) -> dict[str, object] | None:
        if self._anthropic_client is None:
            return None

        prompt = RUNBOOK_SYNTHESIS_PROMPT.format(group_json=json.dumps(group)[:12000])
        try:
            response = await self._anthropic_client.messages.create(
                model=self.config.runbook_synthesis_model,
                max_tokens=self.config.runbook_synthesis_max_tokens,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(getattr(block, "text", "") for block in response.content)
            return _parse_json(text)
        except Exception as exc:
            logger.warning("memory_runbook_synthesis_failed", error=str(exc))
            return None

    async def _replace_runbooks(self, runbooks: list[GeneratedRunbook]) -> None:
        pool = await self.store._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"TRUNCATE TABLE {self.config.runbooks_table_name}"  # nosec B608
                )
                if runbooks:
                    await conn.executemany(
                        f"""  # nosec B608
                        INSERT INTO {self.config.runbooks_table_name} (
                            id,
                            title,
                            trigger_conditions,
                            steps,
                            source_incident_ids,
                            confidence,
                            root_cause_category,
                            services_affected,
                            last_updated
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                        [
                            (
                                runbook.id,
                                runbook.title,
                                runbook.trigger_conditions,
                                runbook.steps,
                                runbook.source_incident_ids,
                                runbook.confidence,
                                runbook.root_cause_category,
                                runbook.services_affected,
                                runbook.last_updated,
                            )
                            for runbook in runbooks
                        ],
                    )


def _fallback_steps(incidents: list[dict[str, object]]) -> list[str]:
    counter: Counter[str] = Counter()
    for incident in incidents:
        steps = incident.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            text = str(step).strip()
            if text:
                counter[text] += 1
    return [step for step, _ in counter.most_common(8)]


def _parse_json(content: str) -> dict[str, object]:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


def _row_to_runbook(row) -> GeneratedRunbook:
    return GeneratedRunbook(
        id=str(row["id"]),
        title=str(row["title"]),
        trigger_conditions=[
            str(item) for item in (row.get("trigger_conditions") or [])
        ],
        steps=[str(item) for item in (row.get("steps") or [])],
        source_incident_ids=[
            str(item) for item in (row.get("source_incident_ids") or [])
        ],
        confidence=float(row["confidence"]),
        root_cause_category=(
            str(row["root_cause_category"]) if row.get("root_cause_category") else None
        ),
        services_affected=[str(item) for item in (row.get("services_affected") or [])],
        last_updated=row["last_updated"],
    )
