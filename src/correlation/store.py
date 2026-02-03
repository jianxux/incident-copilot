"""Redis-backed store for alert groups and correlation state."""

from datetime import datetime, timedelta
from typing import Any

import structlog

from .models import AlertGroup, AlertGroupStatus, CorrelationRule

logger = structlog.get_logger()
KEY_GROUP = "correlation:group:"
KEY_FINGERPRINT = "correlation:fingerprint:"
KEY_RULE = "correlation:rule:"
KEY_ACTIVE_GROUPS = "correlation:active_groups"
KEY_SERVICE_GROUPS = "correlation:service:"


class CorrelationStore:
    def __init__(self, redis_url: str | None = None, group_ttl_seconds: int = 86400):
        self.redis_url = redis_url
        self.group_ttl = group_ttl_seconds
        self._redis: Any = None
        self._memory_store: dict[str, Any] = {}
        self._use_memory = True

    async def initialize(self) -> None:
        if not self.redis_url:
            logger.info("correlation_store_using_memory", reason="no_redis_url")
            return
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self._redis.ping()
            self._use_memory = False
            logger.info("correlation_store_connected")
        except Exception as e:
            logger.warning("correlation_store_redis_failed_using_memory", error=str(e))

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()

    async def store_group(self, group: AlertGroup) -> None:
        key = f"{KEY_GROUP}{group.group_id}"
        data = group.model_dump_json()
        if self._use_memory:
            self._memory_store[key] = data
            if group.status == AlertGroupStatus.ACTIVE:
                self._memory_store.setdefault(KEY_ACTIVE_GROUPS, set()).add(
                    group.group_id
                )
            if group.service:
                self._memory_store.setdefault(
                    f"{KEY_SERVICE_GROUPS}{group.service}", set()
                ).add(group.group_id)
        else:
            await self._redis.setex(key, self.group_ttl, data)
            if group.status == AlertGroupStatus.ACTIVE:
                await self._redis.sadd(KEY_ACTIVE_GROUPS, group.group_id)
            else:
                await self._redis.srem(KEY_ACTIVE_GROUPS, group.group_id)
            if group.service:
                await self._redis.sadd(
                    f"{KEY_SERVICE_GROUPS}{group.service}", group.group_id
                )
        logger.debug(
            "group_stored", group_id=group.group_id, alert_count=group.alert_count
        )

    async def get_group(self, group_id: str) -> AlertGroup | None:
        key = f"{KEY_GROUP}{group_id}"
        data = (
            self._memory_store.get(key)
            if self._use_memory
            else await self._redis.get(key)
        )
        return AlertGroup.model_validate_json(data) if data else None

    async def delete_group(self, group_id: str) -> bool:
        key = f"{KEY_GROUP}{group_id}"
        group = await self.get_group(group_id)
        if self._use_memory:
            if key in self._memory_store:
                del self._memory_store[key]
                self._memory_store.get(KEY_ACTIVE_GROUPS, set()).discard(group_id)
                if group and group.service:
                    self._memory_store.get(
                        f"{KEY_SERVICE_GROUPS}{group.service}", set()
                    ).discard(group_id)
                return True
            return False
        deleted = await self._redis.delete(key)
        await self._redis.srem(KEY_ACTIVE_GROUPS, group_id)
        if group and group.service:
            await self._redis.srem(f"{KEY_SERVICE_GROUPS}{group.service}", group_id)
        if group:
            await self._redis.delete(f"{KEY_FINGERPRINT}{group.fingerprint}")
        return deleted > 0

    async def get_active_groups(
        self, service: str | None = None, limit: int = 100
    ) -> list[AlertGroup]:
        if self._use_memory:
            group_ids = list(
                self._memory_store.get(
                    f"{KEY_SERVICE_GROUPS}{service}" if service else KEY_ACTIVE_GROUPS,
                    set(),
                )
            )[:limit]
        else:
            group_ids = list(
                await self._redis.smembers(
                    f"{KEY_SERVICE_GROUPS}{service}" if service else KEY_ACTIVE_GROUPS
                )
            )[:limit]
        groups = [
            g
            for gid in group_ids
            if (g := await self.get_group(gid)) and g.status == AlertGroupStatus.ACTIVE
        ]
        groups.sort(key=lambda g: g.last_alert_at or g.created_at, reverse=True)
        return groups

    async def store_fingerprint_mapping(
        self, fingerprint: str, group_id: str, expires_at: datetime | None = None
    ) -> None:
        key = f"{KEY_FINGERPRINT}{fingerprint}"
        if self._use_memory:
            self._memory_store[key] = {
                "group_id": group_id,
                "expires_at": expires_at.isoformat() if expires_at else None,
            }
        else:
            ttl = (
                max(1, int((expires_at - datetime.utcnow()).total_seconds()))
                if expires_at
                else self.group_ttl
            )
            await self._redis.setex(key, ttl, group_id)

    async def get_group_by_fingerprint(self, fingerprint: str) -> AlertGroup | None:
        key = f"{KEY_FINGERPRINT}{fingerprint}"
        if self._use_memory:
            mapping = self._memory_store.get(key)
            if mapping:
                if mapping.get(
                    "expires_at"
                ) and datetime.utcnow() > datetime.fromisoformat(mapping["expires_at"]):
                    del self._memory_store[key]
                    return None
                return await self.get_group(mapping["group_id"])
            return None
        group_id = await self._redis.get(key)
        return await self.get_group(group_id) if group_id else None

    async def delete_fingerprint(self, fingerprint: str) -> None:
        key = f"{KEY_FINGERPRINT}{fingerprint}"
        (
            self._memory_store.pop(key, None)
            if self._use_memory
            else await self._redis.delete(key)
        )

    async def store_rule(self, rule: CorrelationRule) -> None:
        key = f"{KEY_RULE}{rule.rule_id}"
        data = rule.model_dump_json()
        if self._use_memory:
            self._memory_store[key] = data
            self._memory_store.setdefault("correlation:rules", set()).add(rule.rule_id)
        else:
            await self._redis.set(key, data)
            await self._redis.sadd("correlation:rules", rule.rule_id)
        logger.info("correlation_rule_stored", rule_id=rule.rule_id, name=rule.name)

    async def get_rule(self, rule_id: str) -> CorrelationRule | None:
        key = f"{KEY_RULE}{rule_id}"
        data = (
            self._memory_store.get(key)
            if self._use_memory
            else await self._redis.get(key)
        )
        return CorrelationRule.model_validate_json(data) if data else None

    async def get_all_rules(self, enabled_only: bool = True) -> list[CorrelationRule]:
        rule_ids = (
            self._memory_store.get("correlation:rules", set())
            if self._use_memory
            else await self._redis.smembers("correlation:rules")
        )
        rules = [
            r
            for rid in rule_ids
            if (r := await self.get_rule(rid)) and (not enabled_only or r.enabled)
        ]
        rules.sort(key=lambda r: r.priority, reverse=True)
        return rules

    async def delete_rule(self, rule_id: str) -> bool:
        key = f"{KEY_RULE}{rule_id}"
        if self._use_memory:
            if key in self._memory_store:
                del self._memory_store[key]
                self._memory_store.get("correlation:rules", set()).discard(rule_id)
                return True
            return False
        deleted = await self._redis.delete(key)
        await self._redis.srem("correlation:rules", rule_id)
        return deleted > 0

    async def cleanup_stale_groups(self, stale_after_seconds: int = 3600) -> int:
        cutoff = datetime.utcnow() - timedelta(seconds=stale_after_seconds)
        groups = await self.get_active_groups(limit=1000)
        count = 0
        for group in groups:
            if (group.last_alert_at or group.created_at) < cutoff:
                group.status = AlertGroupStatus.STALE
                await self.store_group(group)
                count += 1
        if count > 0:
            logger.info("stale_groups_cleaned", count=count)
        return count

    async def get_stats(self) -> dict[str, Any]:
        if self._use_memory:
            return {
                "mode": "memory",
                "active_groups": len(self._memory_store.get(KEY_ACTIVE_GROUPS, set())),
                "rules": len(self._memory_store.get("correlation:rules", set())),
            }
        return {
            "mode": "redis",
            "active_groups": await self._redis.scard(KEY_ACTIVE_GROUPS),
            "rules": await self._redis.scard("correlation:rules"),
        }
