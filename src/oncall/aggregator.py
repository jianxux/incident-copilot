"""Aggregate incident activity for an outgoing on-call shift."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import structlog

from ..config import Settings
from ..integrations.pagerduty.client import PagerDutyClient
from ..integrations.pagerduty.models import PagerDutyConfig, PDStatus
from ..web.store import incident_store
from .models import (
    HandoffAggregate,
    HandoffMetrics,
    IncidentActivityItem,
    ShiftInfo,
)

logger = structlog.get_logger()


class OnCallActivityAggregator:
    """Gather incident/alert activity during a shift window."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def aggregate(self, shift: ShiftInfo) -> HandoffAggregate:
        aggregate = HandoffAggregate(shift=shift, metrics=HandoffMetrics())

        # 1) Local in-memory incident store (always available)
        try:
            stored = await incident_store.get_all_incidents()
            opened = [
                inc
                for inc in stored
                if inc.triggered_at >= shift.shift_start
                and inc.triggered_at <= shift.shift_end
            ]

            aggregate.metrics.incidents_opened += len(opened)
            aggregate.data_sources.append("in_memory_incident_store")

            # Consider "active" as those we have seen that are not in error and are
            # recent enough to matter.
            active = [
                inc
                for inc in stored
                if inc.triggered_at <= shift.shift_end
                and inc.status in {"processing", "completed"}
            ]

            # Map to activity items
            aggregate.active_incidents.extend(
                [
                    IncidentActivityItem(
                        id=inc.incident_id,
                        title=inc.title,
                        status=inc.status,
                        severity=getattr(inc.severity, "value", str(inc.severity)),
                        service=inc.service_name,
                        url=(inc.context_card.alert_url if inc.context_card else None),
                        created_at=inc.triggered_at,
                        updated_at=inc.processed_at,
                        summary=(
                            inc.context_card.ai_summary.explanation
                            if inc.context_card and inc.context_card.ai_summary
                            else None
                        ),
                        raw={"source": "incident_store"},
                    )
                    for inc in active
                ]
            )
        except Exception as e:
            aggregate.errors.append(f"incident_store aggregation failed: {e}")

        # 2) PagerDuty API enrichment (optional)
        if self.settings.pagerduty_api_key:
            try:
                pd_items = await self._aggregate_from_pagerduty(shift)
                aggregate.active_incidents.extend(pd_items["active"])
                aggregate.resolved_incidents.extend(pd_items["resolved"])
                aggregate.metrics.incidents_resolved += len(pd_items["resolved"])
                aggregate.metrics.alerts_acknowledged_unresolved += len(
                    pd_items["ack_unresolved"]
                )

                # Treat escalation heuristically via escalation_level > 1
                aggregate.metrics.incidents_escalated += pd_items["escalated_count"]

                if pd_items["ack_unresolved"]:
                    aggregate.watch_items.append(
                        f"{len(pd_items['ack_unresolved'])} acknowledged PagerDuty incidents still unresolved"
                    )

                aggregate.data_sources.append("pagerduty_api")
            except Exception as e:
                logger.warning("handoff_pd_aggregate_failed", error=str(e))
                aggregate.errors.append(f"pagerduty aggregation failed: {e}")

        # De-dupe by id (PagerDuty may overlap with local store)
        aggregate.active_incidents = self._dedupe_items(aggregate.active_incidents)
        aggregate.resolved_incidents = self._dedupe_items(aggregate.resolved_incidents)

        return aggregate

    async def _aggregate_from_pagerduty(self, shift: ShiftInfo) -> dict:
        config = PagerDutyConfig(
            organization_id=uuid4(),
            api_token=self.settings.pagerduty_api_key,
            integration_key=None,
        )
        client = PagerDutyClient(config)
        try:
            incidents = await client.list_incidents(
                since=shift.shift_start,
                until=shift.shift_end,
                statuses=[PDStatus.TRIGGERED, PDStatus.ACKNOWLEDGED, PDStatus.RESOLVED],
                limit=100,
            )
        finally:
            await client.close()

        active_items: list[IncidentActivityItem] = []
        resolved_items: list[IncidentActivityItem] = []
        ack_unresolved: list[IncidentActivityItem] = []
        escalated_count = 0

        for inc in incidents:
            item = IncidentActivityItem(
                id=inc.id,
                title=inc.title,
                status=inc.status.value,
                severity=inc.urgency.value if getattr(inc, "urgency", None) else None,
                service=inc.service.name if inc.service else None,
                url=inc.html_url,
                created_at=inc.created_at,
                updated_at=inc.updated_at,
                resolved_at=inc.resolved_at,
                raw={"source": "pagerduty", "incident_number": inc.incident_number},
            )

            if inc.status == PDStatus.RESOLVED or inc.resolved_at:
                resolved_items.append(item)
            else:
                active_items.append(item)
                if inc.status == PDStatus.ACKNOWLEDGED:
                    ack_unresolved.append(item)

            if getattr(inc, "escalation_level", 1) and inc.escalation_level > 1:
                escalated_count += 1

        # Also include any active incidents created before shift start but still open.
        # PagerDuty's created_at filter means we can miss those; fetch a small lookback.
        lookback_since = shift.shift_start.replace(tzinfo=UTC) - (
            shift.shift_end - shift.shift_start
        )
        client2 = PagerDutyClient(config)
        try:
            prior = await client2.list_incidents(
                since=lookback_since,
                until=shift.shift_end,
                statuses=[PDStatus.TRIGGERED, PDStatus.ACKNOWLEDGED],
                limit=100,
            )
        finally:
            await client2.close()

        for inc in prior:
            # Only keep those still open at shift end
            if inc.status in {PDStatus.TRIGGERED, PDStatus.ACKNOWLEDGED}:
                active_items.append(
                    IncidentActivityItem(
                        id=inc.id,
                        title=inc.title,
                        status=inc.status.value,
                        severity=(
                            inc.urgency.value if getattr(inc, "urgency", None) else None
                        ),
                        service=inc.service.name if inc.service else None,
                        url=inc.html_url,
                        created_at=inc.created_at,
                        updated_at=inc.updated_at,
                        raw={
                            "source": "pagerduty",
                            "incident_number": inc.incident_number,
                        },
                    )
                )

        return {
            "active": active_items,
            "resolved": resolved_items,
            "ack_unresolved": ack_unresolved,
            "escalated_count": escalated_count,
        }

    def _dedupe_items(
        self, items: list[IncidentActivityItem]
    ) -> list[IncidentActivityItem]:
        seen: set[str] = set()
        out: list[IncidentActivityItem] = []
        for it in sorted(
            items,
            key=lambda x: (
                x.severity or "",
                x.created_at or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        ):
            if it.id in seen:
                continue
            seen.add(it.id)
            out.append(it)
        return out
