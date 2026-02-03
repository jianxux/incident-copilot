"""Core alert correlation engine."""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

import structlog

from ..config import Settings
from ..models import OpsgenieAlert, PagerDutyIncident
from .models import (
    AlertGroup,
    AlertGroupStatus,
    CorrelationResult,
    CorrelationRule,
    IncomingAlert,
)
from .rules import RuleManager, setup_default_rules
from .store import CorrelationStore

logger = structlog.get_logger()


class CorrelationEngine:
    def __init__(
        self,
        settings: Settings,
        store: CorrelationStore | None = None,
        rule_manager: RuleManager | None = None,
    ):
        self.settings = settings
        self.store = store or CorrelationStore(
            redis_url=settings.redis_url,
            group_ttl_seconds=getattr(settings, "correlation_group_ttl", 86400),
        )
        self.rule_manager = rule_manager or RuleManager(self.store)
        self._initialized = False
        self._on_group_created: list[Callable] = []
        self._on_alert_correlated: list[Callable] = []

    async def initialize(self) -> None:
        if self._initialized:
            return
        await self.store.initialize()
        if getattr(self.settings, "correlation_default_rules", True):
            await setup_default_rules(self.store)
        self._initialized = True
        logger.info("correlation_engine_initialized")

    async def close(self) -> None:
        await self.store.close()

    def normalize_pagerduty(self, incident: PagerDutyIncident) -> IncomingAlert:
        return IncomingAlert(
            alert_id=incident.incident_id,
            source="pagerduty",
            title=incident.title,
            description=incident.description,
            service=incident.service_name,
            severity=incident.severity.value,
            triggered_at=incident.triggered_at,
            url=incident.html_url,
            tags=[
                f"service:{incident.service_name}",
                f"severity:{incident.severity.value}",
            ],
            extra={
                "incident_number": incident.incident_number,
                "service_id": incident.service_id,
                "assigned_to": incident.assigned_to,
            },
        )

    def normalize_opsgenie(self, alert: OpsgenieAlert) -> IncomingAlert:
        tags = list(alert.tags) if alert.tags else []
        tags.extend(
            [f"service:{alert.service_name}", f"severity:{alert.severity.value}"]
        )
        return IncomingAlert(
            alert_id=alert.alert_id,
            source="opsgenie",
            title=alert.title,
            description=alert.description,
            service=alert.service_name,
            severity=alert.severity.value,
            tags=tags,
            triggered_at=alert.triggered_at,
            url=alert.url,
            extra={"tiny_id": alert.tiny_id, "source": alert.source},
        )

    async def correlate(self, alert: IncomingAlert) -> CorrelationResult:
        if not self._initialized:
            await self.initialize()
        rule = await self.rule_manager.find_best_rule(alert)
        if not rule:
            return CorrelationResult(alert=alert, correlated=False, should_notify=True)
        existing_group = await self.rule_manager.find_matching_group(alert, rule)
        return (
            await self._add_to_group(alert, existing_group, rule)
            if existing_group
            else await self._create_group(alert, rule)
        )

    async def correlate_pagerduty(
        self, incident: PagerDutyIncident
    ) -> CorrelationResult:
        return await self.correlate(self.normalize_pagerduty(incident))

    async def correlate_opsgenie(
        self, opsgenie_alert: OpsgenieAlert
    ) -> CorrelationResult:
        return await self.correlate(self.normalize_opsgenie(opsgenie_alert))

    async def _add_to_group(
        self, alert: IncomingAlert, group: AlertGroup, rule: CorrelationRule
    ) -> CorrelationResult:
        group.add_alert(alert)
        group.update_summary()
        should_notify, suppression_reason = False, None
        if rule.suppress_duplicates:
            if group.notification_sent:
                if (
                    rule.re_notify_after_seconds > 0
                    and (
                        datetime.utcnow() - (group.first_alert_at or group.created_at)
                    ).total_seconds()
                    >= rule.re_notify_after_seconds
                ):
                    should_notify = True
                else:
                    suppression_reason = (
                        f"Correlated with {group.alert_count-1} other alerts"
                    )
                    group.suppressed_count += 1
            else:
                should_notify = group.alert_count >= rule.max_alerts_before_notify
                if not should_notify:
                    suppression_reason = "Waiting for more alerts"
        else:
            should_notify = True
        await self.store.store_group(group)
        for cb in self._on_alert_correlated:
            try:
                await cb(alert, group)
            except Exception as e:
                logger.error("callback_error", error=str(e))
        logger.info(
            "alert_correlated",
            alert_id=alert.alert_id,
            group_id=group.group_id,
            should_notify=should_notify,
        )
        return CorrelationResult(
            alert=alert,
            correlated=True,
            group=group,
            new_group=False,
            rule_matched=rule,
            should_notify=should_notify,
            suppression_reason=suppression_reason,
        )

    async def _create_group(
        self, alert: IncomingAlert, rule: CorrelationRule
    ) -> CorrelationResult:
        fingerprint = self.rule_manager.generate_fingerprint(alert, rule)
        window_expires = (
            datetime.utcnow() + timedelta(seconds=rule.time_window_seconds)
            if rule.time_window_seconds > 0
            else None
        )
        group = AlertGroup(
            group_id=f"grp_{uuid.uuid4().hex[:12]}",
            rule_id=rule.rule_id,
            strategy=rule.strategy,
            fingerprint=fingerprint,
            window_expires_at=window_expires,
        )
        group.add_alert(alert)
        group.update_summary()
        await self.store.store_group(group)
        await self.store.store_fingerprint_mapping(
            fingerprint, group.group_id, expires_at=window_expires
        )
        should_notify = group.alert_count >= rule.max_alerts_before_notify
        if should_notify:
            group.notification_sent = True
            await self.store.store_group(group)
        for cb in self._on_group_created:
            try:
                await cb(group, alert)
            except Exception as e:
                logger.error("callback_error", error=str(e))
        logger.info(
            "correlation_group_created",
            group_id=group.group_id,
            rule_id=rule.rule_id,
            should_notify=should_notify,
        )
        return CorrelationResult(
            alert=alert,
            correlated=True,
            group=group,
            new_group=True,
            rule_matched=rule,
            should_notify=should_notify,
            suppression_reason=None if should_notify else "Waiting for more alerts",
        )

    async def get_group(self, group_id: str) -> AlertGroup | None:
        return await self.store.get_group(group_id)

    async def get_active_groups(
        self, service: str | None = None, limit: int = 100
    ) -> list[AlertGroup]:
        return await self.store.get_active_groups(service=service, limit=limit)

    async def close_group(
        self, group_id: str, status: AlertGroupStatus = AlertGroupStatus.CLOSED
    ) -> bool:
        group = await self.store.get_group(group_id)
        if not group:
            return False
        group.status, group.updated_at = status, datetime.utcnow()
        await self.store.store_group(group)
        await self.store.delete_fingerprint(group.fingerprint)
        logger.info("correlation_group_closed", group_id=group_id, status=status.value)
        return True

    async def create_rule(self, rule: CorrelationRule) -> CorrelationRule:
        return await self.rule_manager.create_rule(rule)

    async def get_rules(self) -> list[CorrelationRule]:
        return await self.rule_manager.get_rules()

    async def delete_rule(self, rule_id: str) -> bool:
        return await self.rule_manager.delete_rule(rule_id)

    async def cleanup_stale_groups(self) -> int:
        return await self.store.cleanup_stale_groups(
            stale_after_seconds=getattr(
                self.settings, "correlation_stale_after_seconds", 3600
            )
        )

    async def get_stats(self) -> dict:
        return {"initialized": self._initialized, **(await self.store.get_stats())}

    def on_group_created(self, callback: Callable) -> None:
        self._on_group_created.append(callback)

    def on_alert_correlated(self, callback: Callable) -> None:
        self._on_alert_correlated.append(callback)


_engine_instance: CorrelationEngine | None = None


async def get_correlation_engine(settings: Settings) -> CorrelationEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = CorrelationEngine(settings)
        await _engine_instance.initialize()
    return _engine_instance


async def shutdown_correlation_engine() -> None:
    global _engine_instance
    if _engine_instance:
        await _engine_instance.close()
        _engine_instance = None
