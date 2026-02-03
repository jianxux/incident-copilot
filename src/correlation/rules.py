"""Correlation rule management and matching."""

import hashlib
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import structlog
from .models import (
    AlertGroup,
    AlertGroupStatus,
    CorrelationRule,
    CorrelationStrategy,
    IncomingAlert,
)
from .store import CorrelationStore

logger = structlog.get_logger()


def fuzzy_similarity(s1: str, s2: str) -> float:
    if not s1 or not s2:
        return 0.0
    s1, s2 = re.sub(r"[^\w\s]", " ", s1.lower()), re.sub(r"[^\w\s]", " ", s2.lower())
    return SequenceMatcher(None, s1, s2).ratio()


def normalize_title_for_matching(title: str) -> str:
    normalized = title.lower()
    for pattern in [
        r"\d{4}-\d{2}-\d{2}[tT\s]?\d{2}:\d{2}:\d{2}[.\d]*[zZ]?",
        r"\d{4}-\d{2}-\d{2}",
        r"\d{2}:\d{2}:\d{2}",
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        r"[0-9a-f]{32,}",
        r"\d+(\.\d+)?%",
        r"\d+(\.\d+)?\s*(ms|s|sec|seconds?|minutes?|hours?)\b",
        r"\d+\s*(req|requests?|errors?|failures?)\b",
        r"(pod|node|instance)[/-][\w-]+",
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
        r":\d{4,5}\b",
        r"\b\d+\b",
    ]:
        normalized = re.sub(pattern, "", normalized)
    return " ".join(normalized.split()).strip()


class RuleManager:
    def __init__(self, store: CorrelationStore):
        self.store = store
        self._rule_cache: list[CorrelationRule] | None = None
        self._cache_expires: datetime | None = None
        self._cache_ttl = timedelta(seconds=60)

    async def get_rules(self, force_refresh: bool = False) -> list[CorrelationRule]:
        now = datetime.utcnow()
        if (
            not force_refresh
            and self._rule_cache
            and self._cache_expires
            and now < self._cache_expires
        ):
            return self._rule_cache
        self._rule_cache = await self.store.get_all_rules(enabled_only=True)
        self._cache_expires = now + self._cache_ttl
        return self._rule_cache

    async def create_rule(self, rule: CorrelationRule) -> CorrelationRule:
        rule.created_at = rule.updated_at = datetime.utcnow()
        await self.store.store_rule(rule)
        self._rule_cache = None
        return rule

    async def delete_rule(self, rule_id: str) -> bool:
        deleted = await self.store.delete_rule(rule_id)
        if deleted:
            self._rule_cache = None
        return deleted

    def generate_fingerprint(self, alert: IncomingAlert, rule: CorrelationRule) -> str:
        parts = [rule.rule_id]
        if rule.strategy in (
            CorrelationStrategy.TIME_BASED,
            CorrelationStrategy.PATTERN_BASED,
        ):
            parts.extend([alert.service, normalize_title_for_matching(alert.title)])
        elif rule.strategy == CorrelationStrategy.SERVICE_BASED:
            parts.append(alert.service)
        elif rule.strategy == CorrelationStrategy.TAG_BASED:
            parts.append(alert.service)
            for tag_key in rule.group_by_tags:
                for tag in alert.tags:
                    if tag.startswith(f"{tag_key}:") or tag.startswith(f"{tag_key}="):
                        parts.append(tag)
                        break
                else:
                    if tag_key in alert.tags:
                        parts.append(tag_key)
        elif rule.strategy == CorrelationStrategy.COMPOSITE:
            for sub in rule.sub_strategies:
                sub_rule = CorrelationRule(
                    rule_id="temp",
                    name="temp",
                    strategy=sub,
                    group_by_tags=rule.group_by_tags,
                )
                parts.append(self.generate_fingerprint(alert, sub_rule))
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def matches_rule(self, alert: IncomingAlert, rule: CorrelationRule) -> bool:
        if not rule.matches_service(alert.service) or not rule.matches_tags(alert.tags):
            return False
        if rule.title_patterns and not any(
            re.search(p, alert.title, re.IGNORECASE) for p in rule.title_patterns
        ):
            return False
        return True

    async def find_matching_group(
        self, alert: IncomingAlert, rule: CorrelationRule
    ) -> AlertGroup | None:
        fingerprint = self.generate_fingerprint(alert, rule)
        group = await self.store.get_group_by_fingerprint(fingerprint)
        if group and group.status == AlertGroupStatus.ACTIVE:
            if group.window_expires_at and datetime.utcnow() > group.window_expires_at:
                return None
            return group
        if rule.strategy == CorrelationStrategy.PATTERN_BASED:
            normalized_title = normalize_title_for_matching(alert.title)
            for candidate in await self.store.get_active_groups(
                service=alert.service, limit=50
            ):
                if candidate.rule_id == rule.rule_id and candidate.representative_alert:
                    if (
                        fuzzy_similarity(
                            normalized_title,
                            normalize_title_for_matching(
                                candidate.representative_alert.title
                            ),
                        )
                        >= rule.similarity_threshold
                    ):
                        return candidate
        return None

    async def find_best_rule(self, alert: IncomingAlert) -> CorrelationRule | None:
        for rule in await self.get_rules():
            if self.matches_rule(alert, rule):
                return rule
        return None


DEFAULT_RULES = [
    CorrelationRule(
        rule_id="default-service-time",
        name="Service + Time Window",
        description="Group alerts from same service within 5 minute window",
        strategy=CorrelationStrategy.TIME_BASED,
        priority=10,
        time_window_seconds=300,
        suppress_duplicates=True,
    ),
    CorrelationRule(
        rule_id="default-pattern",
        name="Similar Alert Titles",
        description="Group alerts with similar titles (fuzzy match)",
        strategy=CorrelationStrategy.PATTERN_BASED,
        priority=5,
        time_window_seconds=600,
        similarity_threshold=0.7,
        suppress_duplicates=True,
    ),
]


async def setup_default_rules(store: CorrelationStore) -> None:
    if await store.get_all_rules(enabled_only=False):
        logger.info("correlation_rules_exist")
        return
    logger.info("setting_up_default_correlation_rules")
    for rule in DEFAULT_RULES:
        await store.store_rule(rule)
