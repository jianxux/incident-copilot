"""SLA Data Store.

Provides Redis (hot data) and PostgreSQL (persistent) storage for SLA data.
Supports caching, async operations, and efficient querying.
"""

import json
import logging
from datetime import datetime
from typing import Any

from .models import (
    EscalationLevel,
    SLABreach,
    SLAPolicy,
    SLASeverity,
    SLAStatus,
    SLATimer,
    SLAType,
)

logger = logging.getLogger(__name__)


class SLAStore:
    """Storage layer for SLA data.

    Uses Redis for:
    - Active timers (hot data, needs fast access)
    - Timer caching
    - Policy caching

    Uses PostgreSQL for:
    - SLA policies (persistent)
    - Breach history (persistent)
    - Completed timers (for metrics)
    """

    # Redis key prefixes
    TIMER_PREFIX = "sla:timer"
    POLICY_PREFIX = "sla:policy"
    BREACH_PREFIX = "sla:breach"
    ACTIVE_TIMERS_SET = "sla:active_timers"

    def __init__(
        self,
        redis_client: Any = None,
        db_pool: Any = None,
    ) -> None:
        """Initialize SLA store.

        Args:
            redis_client: Redis async client (aioredis)
            db_pool: PostgreSQL connection pool (asyncpg)
        """
        self.redis = redis_client
        self.db = db_pool
        self._use_redis = redis_client is not None
        self._use_db = db_pool is not None

    # --- Timer Operations ---

    async def save_timer(self, timer: SLATimer) -> None:
        """Save or update an SLA timer.

        Args:
            timer: Timer to save
        """
        key = f"{self.TIMER_PREFIX}:{timer.incident_id}:{timer.sla_type}"
        data = timer.model_dump(mode="json")

        if self._use_redis:
            await self.redis.set(key, json.dumps(data))
            # Track active timers
            if not timer.completed_at:
                await self.redis.sadd(
                    self.ACTIVE_TIMERS_SET,
                    f"{timer.incident_id}:{timer.sla_type}",
                )
            else:
                await self.redis.srem(
                    self.ACTIVE_TIMERS_SET,
                    f"{timer.incident_id}:{timer.sla_type}",
                )

        if self._use_db:
            await self._upsert_timer_db(timer)

    async def get_timer(self, incident_id: str, sla_type: SLAType) -> SLATimer | None:
        """Get an SLA timer.

        Args:
            incident_id: Incident identifier
            sla_type: Response or resolution

        Returns:
            Timer if found, None otherwise
        """
        key = f"{self.TIMER_PREFIX}:{incident_id}:{sla_type}"

        # Try Redis first
        if self._use_redis:
            data = await self.redis.get(key)
            if data:
                return SLATimer.model_validate(json.loads(data))

        # Fall back to database
        if self._use_db:
            return await self._get_timer_db(incident_id, sla_type)

        return None

    async def get_incident_timers(self, incident_id: str) -> list[SLATimer]:
        """Get all timers for an incident.

        Args:
            incident_id: Incident identifier

        Returns:
            List of timers (response and/or resolution)
        """
        timers: list[SLATimer] = []

        for sla_type in SLAType:
            timer = await self.get_timer(incident_id, sla_type)
            if timer:
                timers.append(timer)

        return timers

    async def get_active_timers(self) -> list[SLATimer]:
        """Get all active (non-completed) timers.

        Returns:
            List of active timers
        """
        timers: list[SLATimer] = []

        if self._use_redis:
            members = await self.redis.smembers(self.ACTIVE_TIMERS_SET)
            for member in members:
                if isinstance(member, bytes):
                    member = member.decode()
                parts = member.rsplit(":", 1)
                if len(parts) == 2:
                    incident_id, sla_type = parts
                    timer = await self.get_timer(incident_id, SLAType(sla_type))
                    if timer and not timer.completed_at:
                        timers.append(timer)
        elif self._use_db:
            timers = await self._get_active_timers_db()

        return timers

    async def get_timers_in_period(
        self,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
        team_id: str | None = None,
        service_id: str | None = None,
        policy_id: str | None = None,
    ) -> list[SLATimer]:
        """Get timers within a time period for metrics.

        Args:
            organization_id: Organization scope
            period_start: Start of period
            period_end: End of period
            team_id: Optional team filter
            service_id: Optional service filter
            policy_id: Optional policy filter

        Returns:
            List of timers in the period
        """
        if not self._use_db:
            # Without DB, return empty (can't query Redis efficiently)
            return []

        return await self._get_timers_in_period_db(
            organization_id, period_start, period_end, team_id, service_id, policy_id
        )

    async def delete_timer(self, incident_id: str, sla_type: SLAType) -> bool:
        """Delete an SLA timer.

        Args:
            incident_id: Incident identifier
            sla_type: Timer type to delete

        Returns:
            True if deleted, False if not found
        """
        key = f"{self.TIMER_PREFIX}:{incident_id}:{sla_type}"

        deleted = False
        if self._use_redis:
            result = await self.redis.delete(key)
            await self.redis.srem(
                self.ACTIVE_TIMERS_SET,
                f"{incident_id}:{sla_type}",
            )
            deleted = result > 0

        if self._use_db:
            deleted = await self._delete_timer_db(incident_id, sla_type)

        return deleted

    # --- Policy Operations ---

    async def save_policy(self, policy: SLAPolicy) -> None:
        """Save or update an SLA policy.

        Args:
            policy: Policy to save
        """
        policy.updated_at = datetime.utcnow()
        data = policy.model_dump(mode="json")

        if self._use_redis:
            key = f"{self.POLICY_PREFIX}:{policy.id}"
            await self.redis.set(key, json.dumps(data), ex=3600)  # 1hr cache

        if self._use_db:
            await self._upsert_policy_db(policy)

    async def get_policy(self, policy_id: str) -> SLAPolicy | None:
        """Get an SLA policy by ID.

        Args:
            policy_id: Policy identifier

        Returns:
            Policy if found, None otherwise
        """
        # Try Redis cache
        if self._use_redis:
            key = f"{self.POLICY_PREFIX}:{policy_id}"
            data = await self.redis.get(key)
            if data:
                return SLAPolicy.model_validate(json.loads(data))

        # Fall back to database
        if self._use_db:
            policy = await self._get_policy_db(policy_id)
            if policy and self._use_redis:
                # Cache for next time
                key = f"{self.POLICY_PREFIX}:{policy_id}"
                await self.redis.set(
                    key, json.dumps(policy.model_dump(mode="json")), ex=3600
                )
            return policy

        return None

    async def get_policies(
        self,
        organization_id: str,
        team_id: str | None = None,
        service_id: str | None = None,
        active_only: bool = True,
    ) -> list[SLAPolicy]:
        """Get SLA policies with optional filters.

        Args:
            organization_id: Organization scope
            team_id: Optional team filter
            service_id: Optional service filter
            active_only: Only return active policies

        Returns:
            List of matching policies
        """
        if not self._use_db:
            return []

        return await self._get_policies_db(
            organization_id, team_id, service_id, active_only
        )

    async def delete_policy(self, policy_id: str) -> bool:
        """Delete an SLA policy.

        Args:
            policy_id: Policy to delete

        Returns:
            True if deleted
        """
        if self._use_redis:
            key = f"{self.POLICY_PREFIX}:{policy_id}"
            await self.redis.delete(key)

        if self._use_db:
            return await self._delete_policy_db(policy_id)

        return False

    # --- Breach Operations ---

    async def save_breach(self, breach: SLABreach) -> None:
        """Save an SLA breach record.

        Args:
            breach: Breach to save
        """
        data = breach.model_dump(mode="json")

        if self._use_redis:
            key = f"{self.BREACH_PREFIX}:{breach.id}"
            await self.redis.set(key, json.dumps(data), ex=86400 * 7)  # 7 days

            # Index by incident
            incident_key = f"{self.BREACH_PREFIX}:incident:{breach.incident_id}"
            await self.redis.sadd(incident_key, breach.id)

        if self._use_db:
            await self._insert_breach_db(breach)

    async def get_breach(self, incident_id: str, sla_type: SLAType) -> SLABreach | None:
        """Get a breach record for an incident/type.

        Args:
            incident_id: Incident identifier
            sla_type: Response or resolution

        Returns:
            Breach if found
        """
        breaches = await self.get_incident_breaches(incident_id)
        for breach in breaches:
            if breach.sla_type == sla_type:
                return breach
        return None

    async def get_incident_breaches(self, incident_id: str) -> list[SLABreach]:
        """Get all breaches for an incident.

        Args:
            incident_id: Incident identifier

        Returns:
            List of breaches
        """
        breaches: list[SLABreach] = []

        if self._use_redis:
            incident_key = f"{self.BREACH_PREFIX}:incident:{incident_id}"
            breach_ids = await self.redis.smembers(incident_key)

            for bid in breach_ids:
                if isinstance(bid, bytes):
                    bid = bid.decode()
                key = f"{self.BREACH_PREFIX}:{bid}"
                data = await self.redis.get(key)
                if data:
                    breaches.append(SLABreach.model_validate(json.loads(data)))

        if not breaches and self._use_db:
            breaches = await self._get_incident_breaches_db(incident_id)

        return breaches

    async def get_breaches_in_period(
        self,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
        severity: SLASeverity | None = None,
        sla_type: SLAType | None = None,
    ) -> list[SLABreach]:
        """Get breaches in a time period.

        Args:
            organization_id: Organization scope
            period_start: Start of period
            period_end: End of period
            severity: Optional severity filter
            sla_type: Optional type filter

        Returns:
            List of breaches
        """
        if not self._use_db:
            return []

        return await self._get_breaches_in_period_db(
            organization_id, period_start, period_end, severity, sla_type
        )

    async def acknowledge_breach(self, breach_id: str, user: str) -> SLABreach | None:
        """Acknowledge a breach.

        Args:
            breach_id: Breach to acknowledge
            user: User acknowledging

        Returns:
            Updated breach
        """
        if self._use_redis:
            key = f"{self.BREACH_PREFIX}:{breach_id}"
            data = await self.redis.get(key)
            if data:
                breach = SLABreach.model_validate(json.loads(data))
                breach.acknowledged_at = datetime.utcnow()
                breach.acknowledged_by = user
                await self.redis.set(key, json.dumps(breach.model_dump(mode="json")))
                if self._use_db:
                    await self._update_breach_db(breach)
                return breach

        if self._use_db:
            return await self._acknowledge_breach_db(breach_id, user)

        return None

    # --- Private Database Methods ---

    async def _upsert_timer_db(self, timer: SLATimer) -> None:
        """Upsert timer to PostgreSQL."""
        if not self.db:
            return

        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sla_timers (
                    incident_id, policy_id, severity, sla_type,
                    started_at, target_minutes, elapsed_minutes,
                    paused, paused_at, total_paused_minutes,
                    status, breached_at, completed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (incident_id, sla_type) DO UPDATE SET
                    elapsed_minutes = EXCLUDED.elapsed_minutes,
                    paused = EXCLUDED.paused,
                    paused_at = EXCLUDED.paused_at,
                    total_paused_minutes = EXCLUDED.total_paused_minutes,
                    status = EXCLUDED.status,
                    breached_at = EXCLUDED.breached_at,
                    completed_at = EXCLUDED.completed_at
                """,
                timer.incident_id,
                timer.policy_id,
                timer.severity.value,
                timer.sla_type.value,
                timer.started_at,
                timer.target_minutes,
                timer.elapsed_minutes,
                timer.paused,
                timer.paused_at,
                timer.total_paused_minutes,
                timer.status.value,
                timer.breached_at,
                timer.completed_at,
            )

    async def _get_timer_db(
        self, incident_id: str, sla_type: SLAType
    ) -> SLATimer | None:
        """Get timer from PostgreSQL."""
        if not self.db:
            return None

        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM sla_timers
                WHERE incident_id = $1 AND sla_type = $2
                """,
                incident_id,
                sla_type.value,
            )
            if row:
                return self._row_to_timer(row)
        return None

    async def _get_active_timers_db(self) -> list[SLATimer]:
        """Get active timers from PostgreSQL."""
        if not self.db:
            return []

        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM sla_timers
                WHERE completed_at IS NULL
                ORDER BY started_at ASC
                """)
            return [self._row_to_timer(row) for row in rows]

    async def _get_timers_in_period_db(
        self,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
        team_id: str | None,
        service_id: str | None,
        policy_id: str | None,
    ) -> list[SLATimer]:
        """Get timers in period from PostgreSQL."""
        if not self.db:
            return []

        query = """
            SELECT t.* FROM sla_timers t
            JOIN sla_policies p ON t.policy_id = p.id
            WHERE t.started_at >= $1 AND t.started_at < $2
            AND p.organization_id = $3
        """
        params: list[Any] = [period_start, period_end, organization_id]
        idx = 4

        if team_id:
            query += f" AND p.team_id = ${idx}"
            params.append(team_id)
            idx += 1
        if service_id:
            query += f" AND p.service_id = ${idx}"
            params.append(service_id)
            idx += 1
        if policy_id:
            query += f" AND t.policy_id = ${idx}"
            params.append(policy_id)

        async with self.db.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [self._row_to_timer(row) for row in rows]

    async def _delete_timer_db(self, incident_id: str, sla_type: SLAType) -> bool:
        """Delete timer from PostgreSQL."""
        if not self.db:
            return False

        async with self.db.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM sla_timers
                WHERE incident_id = $1 AND sla_type = $2
                """,
                incident_id,
                sla_type.value,
            )
            return "DELETE 1" in result

    async def _upsert_policy_db(self, policy: SLAPolicy) -> None:
        """Upsert policy to PostgreSQL."""
        if not self.db:
            return

        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sla_policies (
                    id, name, description, organization_id, team_id, service_id,
                    targets, business_hours, escalation_enabled, escalation_contacts,
                    is_active, created_at, updated_at, created_by
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    targets = EXCLUDED.targets,
                    business_hours = EXCLUDED.business_hours,
                    escalation_enabled = EXCLUDED.escalation_enabled,
                    escalation_contacts = EXCLUDED.escalation_contacts,
                    is_active = EXCLUDED.is_active,
                    updated_at = EXCLUDED.updated_at
                """,
                policy.id,
                policy.name,
                policy.description,
                policy.organization_id,
                policy.team_id,
                policy.service_id,
                json.dumps([t.model_dump(mode="json") for t in policy.targets]),
                json.dumps(policy.business_hours.model_dump(mode="json")),
                policy.escalation_enabled,
                json.dumps(policy.escalation_contacts),
                policy.is_active,
                policy.created_at,
                policy.updated_at,
                policy.created_by,
            )

    async def _get_policy_db(self, policy_id: str) -> SLAPolicy | None:
        """Get policy from PostgreSQL."""
        if not self.db:
            return None

        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sla_policies WHERE id = $1",
                policy_id,
            )
            if row:
                return self._row_to_policy(row)
        return None

    async def _get_policies_db(
        self,
        organization_id: str,
        team_id: str | None,
        service_id: str | None,
        active_only: bool,
    ) -> list[SLAPolicy]:
        """Get policies from PostgreSQL with filters."""
        if not self.db:
            return []

        query = "SELECT * FROM sla_policies WHERE organization_id = $1"
        params: list[Any] = [organization_id]
        idx = 2

        if team_id:
            query += f" AND team_id = ${idx}"
            params.append(team_id)
            idx += 1
        if service_id:
            query += f" AND service_id = ${idx}"
            params.append(service_id)
            idx += 1
        if active_only:
            query += " AND is_active = true"

        query += " ORDER BY created_at DESC"

        async with self.db.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [self._row_to_policy(row) for row in rows]

    async def _delete_policy_db(self, policy_id: str) -> bool:
        """Delete policy from PostgreSQL."""
        if not self.db:
            return False

        async with self.db.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM sla_policies WHERE id = $1",
                policy_id,
            )
            return "DELETE 1" in result

    async def _insert_breach_db(self, breach: SLABreach) -> None:
        """Insert breach to PostgreSQL."""
        if not self.db:
            return

        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sla_breaches (
                    id, incident_id, policy_id, severity, sla_type,
                    target_minutes, actual_minutes, breach_amount_minutes,
                    breach_percent, escalation_level, escalated_to,
                    escalation_sent_at, breached_at, resolved_at,
                    acknowledged_at, acknowledged_by, notes, root_cause
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                """,
                breach.id,
                breach.incident_id,
                breach.policy_id,
                breach.severity.value,
                breach.sla_type.value,
                breach.target_minutes,
                breach.actual_minutes,
                breach.breach_amount_minutes,
                breach.breach_percent,
                breach.escalation_level.value,
                json.dumps(breach.escalated_to),
                breach.escalation_sent_at,
                breach.breached_at,
                breach.resolved_at,
                breach.acknowledged_at,
                breach.acknowledged_by,
                breach.notes,
                breach.root_cause,
            )

    async def _get_incident_breaches_db(self, incident_id: str) -> list[SLABreach]:
        """Get breaches for an incident from PostgreSQL."""
        if not self.db:
            return []

        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM sla_breaches WHERE incident_id = $1",
                incident_id,
            )
            return [self._row_to_breach(row) for row in rows]

    async def _get_breaches_in_period_db(
        self,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
        severity: SLASeverity | None,
        sla_type: SLAType | None,
    ) -> list[SLABreach]:
        """Get breaches in period from PostgreSQL."""
        if not self.db:
            return []

        query = """
            SELECT b.* FROM sla_breaches b
            JOIN sla_policies p ON b.policy_id = p.id
            WHERE b.breached_at >= $1 AND b.breached_at < $2
            AND p.organization_id = $3
        """
        params: list[Any] = [period_start, period_end, organization_id]
        idx = 4

        if severity:
            query += f" AND b.severity = ${idx}"
            params.append(severity.value)
            idx += 1
        if sla_type:
            query += f" AND b.sla_type = ${idx}"
            params.append(sla_type.value)

        query += " ORDER BY b.breached_at DESC"

        async with self.db.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [self._row_to_breach(row) for row in rows]

    async def _acknowledge_breach_db(
        self, breach_id: str, user: str
    ) -> SLABreach | None:
        """Acknowledge breach in PostgreSQL."""
        if not self.db:
            return None

        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE sla_breaches
                SET acknowledged_at = $1, acknowledged_by = $2
                WHERE id = $3
                """,
                datetime.utcnow(),
                user,
                breach_id,
            )
            row = await conn.fetchrow(
                "SELECT * FROM sla_breaches WHERE id = $1",
                breach_id,
            )
            if row:
                return self._row_to_breach(row)
        return None

    async def _update_breach_db(self, breach: SLABreach) -> None:
        """Update breach in PostgreSQL."""
        if not self.db:
            return

        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE sla_breaches
                SET resolved_at = $1, acknowledged_at = $2,
                    acknowledged_by = $3, notes = $4, root_cause = $5
                WHERE id = $6
                """,
                breach.resolved_at,
                breach.acknowledged_at,
                breach.acknowledged_by,
                breach.notes,
                breach.root_cause,
                breach.id,
            )

    # --- Row Conversion Helpers ---

    def _row_to_timer(self, row: Any) -> SLATimer:
        """Convert database row to SLATimer."""
        return SLATimer(
            incident_id=row["incident_id"],
            policy_id=row["policy_id"],
            severity=SLASeverity(row["severity"]),
            sla_type=SLAType(row["sla_type"]),
            started_at=row["started_at"],
            target_minutes=row["target_minutes"],
            elapsed_minutes=row["elapsed_minutes"],
            paused=row["paused"],
            paused_at=row["paused_at"],
            total_paused_minutes=row["total_paused_minutes"],
            status=SLAStatus(row["status"]),
            breached_at=row["breached_at"],
            completed_at=row["completed_at"],
        )

    def _row_to_policy(self, row: Any) -> SLAPolicy:
        """Convert database row to SLAPolicy."""
        from .models import BusinessHours, SLATarget

        targets_data = row["targets"]
        if isinstance(targets_data, str):
            targets_data = json.loads(targets_data)
        targets = [SLATarget.model_validate(t) for t in targets_data]

        bh_data = row["business_hours"]
        if isinstance(bh_data, str):
            bh_data = json.loads(bh_data)
        business_hours = BusinessHours.model_validate(bh_data)

        contacts = row["escalation_contacts"]
        if isinstance(contacts, str):
            contacts = json.loads(contacts)

        return SLAPolicy(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            organization_id=row["organization_id"],
            team_id=row["team_id"],
            service_id=row["service_id"],
            targets=targets,
            business_hours=business_hours,
            escalation_enabled=row["escalation_enabled"],
            escalation_contacts=contacts,
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by=row["created_by"],
        )

    def _row_to_breach(self, row: Any) -> SLABreach:
        """Convert database row to SLABreach."""
        escalated_to = row["escalated_to"]
        if isinstance(escalated_to, str):
            escalated_to = json.loads(escalated_to)

        return SLABreach(
            id=row["id"],
            incident_id=row["incident_id"],
            policy_id=row["policy_id"],
            severity=SLASeverity(row["severity"]),
            sla_type=SLAType(row["sla_type"]),
            target_minutes=row["target_minutes"],
            actual_minutes=row["actual_minutes"],
            breach_amount_minutes=row["breach_amount_minutes"],
            breach_percent=row["breach_percent"],
            escalation_level=EscalationLevel(row["escalation_level"]),
            escalated_to=escalated_to,
            escalation_sent_at=row["escalation_sent_at"],
            breached_at=row["breached_at"],
            resolved_at=row["resolved_at"],
            acknowledged_at=row["acknowledged_at"],
            acknowledged_by=row["acknowledged_by"],
            notes=row["notes"],
            root_cause=row["root_cause"],
        )


# SQL schema for reference
SCHEMA_SQL = """
-- SLA Policies
CREATE TABLE IF NOT EXISTS sla_policies (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    organization_id VARCHAR(64) NOT NULL,
    team_id VARCHAR(64),
    service_id VARCHAR(64),
    targets JSONB NOT NULL DEFAULT '[]',
    business_hours JSONB NOT NULL DEFAULT '{}',
    escalation_enabled BOOLEAN DEFAULT TRUE,
    escalation_contacts JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(64)
);

CREATE INDEX idx_sla_policies_org ON sla_policies(organization_id);
CREATE INDEX idx_sla_policies_team ON sla_policies(team_id);
CREATE INDEX idx_sla_policies_service ON sla_policies(service_id);

-- SLA Timers
CREATE TABLE IF NOT EXISTS sla_timers (
    incident_id VARCHAR(64) NOT NULL,
    policy_id VARCHAR(64) NOT NULL REFERENCES sla_policies(id),
    severity VARCHAR(10) NOT NULL,
    sla_type VARCHAR(20) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    target_minutes INTEGER NOT NULL,
    elapsed_minutes FLOAT DEFAULT 0,
    paused BOOLEAN DEFAULT FALSE,
    paused_at TIMESTAMP WITH TIME ZONE,
    total_paused_minutes FLOAT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'on_track',
    breached_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (incident_id, sla_type)
);

CREATE INDEX idx_sla_timers_policy ON sla_timers(policy_id);
CREATE INDEX idx_sla_timers_status ON sla_timers(status);
CREATE INDEX idx_sla_timers_started ON sla_timers(started_at);

-- SLA Breaches
CREATE TABLE IF NOT EXISTS sla_breaches (
    id VARCHAR(64) PRIMARY KEY,
    incident_id VARCHAR(64) NOT NULL,
    policy_id VARCHAR(64) NOT NULL REFERENCES sla_policies(id),
    severity VARCHAR(10) NOT NULL,
    sla_type VARCHAR(20) NOT NULL,
    target_minutes INTEGER NOT NULL,
    actual_minutes FLOAT NOT NULL,
    breach_amount_minutes FLOAT NOT NULL,
    breach_percent FLOAT NOT NULL,
    escalation_level VARCHAR(20) NOT NULL,
    escalated_to JSONB DEFAULT '[]',
    escalation_sent_at TIMESTAMP WITH TIME ZONE,
    breached_at TIMESTAMP WITH TIME ZONE NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    acknowledged_by VARCHAR(64),
    notes TEXT,
    root_cause TEXT
);

CREATE INDEX idx_sla_breaches_incident ON sla_breaches(incident_id);
CREATE INDEX idx_sla_breaches_policy ON sla_breaches(policy_id);
CREATE INDEX idx_sla_breaches_breached ON sla_breaches(breached_at);
"""
