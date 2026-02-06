"""Core Escalation Rules Engine.

Evaluates conditions, triggers actions, and manages escalation state.
"""

import asyncio
import re
from datetime import datetime
from typing import Any

import structlog

from .actions import ActionResult, execute_actions
from .conditions import evaluate_conditions
from .models import (
    EscalationAuditEntry,
    EscalationPolicy,
    EscalationResult,
    EscalationRule,
    EscalationStep,
    IncidentState,
    MaintenanceWindow,
)

logger = structlog.get_logger()


class EscalationStore:
    """In-memory store for escalation policies and state.

    In production, this would be backed by Redis or a database.
    """

    def __init__(self):
        self._policies: dict[str, EscalationPolicy] = {}
        self._rules: dict[str, EscalationRule] = {}
        self._maintenance_windows: dict[str, MaintenanceWindow] = {}
        self._incident_states: dict[str, IncidentState] = {}
        self._audit_log: list[EscalationAuditEntry] = []
        self._escalation_history: dict[str, list[dict]] = {}  # incident_id -> history

    async def initialize(self) -> None:
        """Initialize the store (connect to Redis, etc.)."""
        logger.info("escalation_store_initialized")

    async def close(self) -> None:
        """Close store connections."""
        logger.info("escalation_store_closed")

    # Policy methods
    async def store_policy(self, policy: EscalationPolicy) -> EscalationPolicy:
        self._policies[policy.id] = policy
        return policy

    async def get_policy(self, policy_id: str) -> EscalationPolicy | None:
        return self._policies.get(policy_id)

    async def delete_policy(self, policy_id: str) -> bool:
        if policy_id in self._policies:
            del self._policies[policy_id]
            return True
        return False

    async def list_policies(
        self,
        tenant_id: str | None = None,
        service_id: str | None = None,
        team_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[EscalationPolicy], int]:
        policies = list(self._policies.values())

        # Filter
        if tenant_id:
            policies = [p for p in policies if p.tenant_id == tenant_id]
        if service_id:
            policies = [p for p in policies if p.service_id == service_id]
        if team_id:
            policies = [p for p in policies if p.team_id == team_id]

        total = len(policies)
        return policies[offset : offset + limit], total

    # Rule methods
    async def store_rule(self, rule: EscalationRule) -> EscalationRule:
        self._rules[rule.id] = rule
        return rule

    async def get_rule(self, rule_id: str) -> EscalationRule | None:
        return self._rules.get(rule_id)

    async def delete_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    async def list_rules(
        self,
        enabled_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[EscalationRule], int]:
        rules = list(self._rules.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        # Sort by priority (lower = higher priority)
        rules.sort(key=lambda r: r.priority)
        total = len(rules)
        return rules[offset : offset + limit], total

    # Maintenance window methods
    async def store_maintenance_window(
        self, window: MaintenanceWindow
    ) -> MaintenanceWindow:
        self._maintenance_windows[window.id] = window
        return window

    async def get_active_maintenance_windows(
        self,
        service: str | None = None,
        team_id: str | None = None,
        at_time: datetime | None = None,
    ) -> list[MaintenanceWindow]:
        check_time = at_time or datetime.utcnow()
        active = []
        for window in self._maintenance_windows.values():
            if not window.is_active(check_time):
                continue
            # Check service match
            if service:
                if window.service_id and window.service_id != service:
                    continue
                if window.service_pattern and not re.match(
                    window.service_pattern, service
                ):
                    continue
            # Check team match
            if team_id and window.team_id and window.team_id != team_id:
                continue
            active.append(window)
        return active

    async def delete_maintenance_window(self, window_id: str) -> bool:
        if window_id in self._maintenance_windows:
            del self._maintenance_windows[window_id]
            return True
        return False

    # Incident state methods
    async def store_incident_state(self, state: IncidentState) -> IncidentState:
        self._incident_states[state.incident_id] = state
        return state

    async def get_incident_state(self, incident_id: str) -> IncidentState | None:
        return self._incident_states.get(incident_id)

    async def list_active_incidents(
        self, limit: int = 100
    ) -> list[IncidentState]:
        return [
            s for s in list(self._incident_states.values())[:limit]
            if not s.is_resolved
        ]

    async def update_incident_escalation(
        self,
        incident_id: str,
        step: int,
        policy_id: str | None = None,
    ) -> None:
        state = self._incident_states.get(incident_id)
        if state:
            state.current_escalation_step = step
            state.last_escalation_at = datetime.utcnow()
            state.escalation_count += 1
            if policy_id:
                state.escalation_policy_id = policy_id

    # Audit log methods
    async def store_audit_entry(self, entry: EscalationAuditEntry) -> None:
        self._audit_log.append(entry)
        # Keep last 10000 entries in memory
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-10000:]

    async def get_audit_log(
        self,
        incident_id: str | None = None,
        policy_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[EscalationAuditEntry], int]:
        entries = self._audit_log
        if incident_id:
            entries = [e for e in entries if e.incident_id == incident_id]
        if policy_id:
            entries = [e for e in entries if e.policy_id == policy_id]
        # Sort by timestamp descending
        entries = sorted(entries, key=lambda e: e.timestamp, reverse=True)
        total = len(entries)
        return entries[offset : offset + limit], total

    # Escalation history
    async def record_escalation(
        self, incident_id: str, step: int, policy_id: str, actions: list[str]
    ) -> None:
        if incident_id not in self._escalation_history:
            self._escalation_history[incident_id] = []
        self._escalation_history[incident_id].append({
            "step": step,
            "policy_id": policy_id,
            "actions": actions,
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def get_escalation_history(self, incident_id: str) -> list[dict]:
        return self._escalation_history.get(incident_id, [])


class EscalationEngine:
    """Core engine for evaluating and executing escalation rules."""

    def __init__(
        self,
        store: EscalationStore | None = None,
        settings: Any | None = None,
    ):
        self.store = store or EscalationStore()
        self.settings = settings
        self._initialized = False
        self._callbacks: dict[str, list] = {
            "on_escalation": [],
            "on_action_executed": [],
            "on_suppressed": [],
        }

    async def initialize(self) -> None:
        """Initialize the engine."""
        if self._initialized:
            return
        await self.store.initialize()
        self._initialized = True
        logger.info("escalation_engine_initialized")

    async def close(self) -> None:
        """Shutdown the engine."""
        await self.store.close()
        self._initialized = False
        logger.info("escalation_engine_closed")

    def on_escalation(self, callback) -> None:
        """Register callback for escalation events."""
        self._callbacks["on_escalation"].append(callback)

    def on_action_executed(self, callback) -> None:
        """Register callback for action execution events."""
        self._callbacks["on_action_executed"].append(callback)

    def on_suppressed(self, callback) -> None:
        """Register callback for suppressed escalation events."""
        self._callbacks["on_suppressed"].append(callback)

    async def _emit(self, event: str, *args, **kwargs) -> None:
        """Emit event to registered callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                logger.error("callback_error", event=event, error=str(e))

    async def evaluate_incident(
        self, incident: IncidentState
    ) -> EscalationResult:
        """Evaluate an incident for escalation.

        Args:
            incident: The current incident state

        Returns:
            EscalationResult with triggered actions
        """
        if not self._initialized:
            await self.initialize()

        # Store incident state
        await self.store.store_incident_state(incident)

        # Check for maintenance window suppression
        suppression_reason = await self._check_maintenance_window(incident)
        if suppression_reason:
            result = EscalationResult(
                incident_id=incident.incident_id,
                triggered=False,
                suppressed=True,
                suppression_reason=suppression_reason,
            )
            await self._emit("on_suppressed", incident, result)
            return result

        # Check for resolved incidents
        if incident.is_resolved:
            return EscalationResult(
                incident_id=incident.incident_id,
                triggered=False,
                suppression_reason="Incident is resolved",
            )

        # Find matching policy
        policy = await self._find_matching_policy(incident)

        if policy:
            return await self._evaluate_policy(incident, policy)

        # Fall back to rules-based evaluation
        return await self._evaluate_rules(incident)

    async def _check_maintenance_window(
        self, incident: IncidentState
    ) -> str | None:
        """Check if incident is within a maintenance window."""
        windows = await self.store.get_active_maintenance_windows(
            service=incident.service,
            team_id=incident.team_id,
        )
        for window in windows:
            if window.suppress_escalations:
                return f"In maintenance window: {window.name}"
        return None

    async def _find_matching_policy(
        self, incident: IncidentState
    ) -> EscalationPolicy | None:
        """Find the best matching escalation policy for an incident."""
        policies, _ = await self.store.list_policies(
            tenant_id=incident.tenant_id,
        )

        best_match: EscalationPolicy | None = None
        best_score = -1

        for policy in policies:
            if not policy.enabled:
                continue

            score = self._calculate_policy_match_score(policy, incident)
            if score > best_score:
                best_score = score
                best_match = policy

        return best_match

    def _calculate_policy_match_score(
        self, policy: EscalationPolicy, incident: IncidentState
    ) -> int:
        """Calculate how well a policy matches an incident.

        Higher score = better match. Returns -1 for no match.
        """
        score = 0

        # Exact service match is highest priority
        if policy.service_id:
            if policy.service_id == incident.service:
                score += 100
            else:
                return -1  # No match

        # Service pattern match
        if policy.service_pattern:
            if re.match(policy.service_pattern, incident.service):
                score += 50
            else:
                return -1

        # Team match
        if policy.team_id:
            if policy.team_id == incident.team_id:
                score += 30
            else:
                return -1

        # Service tier match
        if policy.service_tier:
            if incident.service_tier == policy.service_tier:
                score += 20
            elif incident.service_tier is None:
                pass  # No tier info, don't penalize
            else:
                return -1

        return score

    async def _evaluate_policy(
        self, incident: IncidentState, policy: EscalationPolicy
    ) -> EscalationResult:
        """Evaluate incident against a policy."""
        # Check business hours restriction
        if policy.business_hours_only and not self._is_business_hours(policy):
            return EscalationResult(
                incident_id=incident.incident_id,
                triggered=False,
                policy_id=policy.id,
                suppressed=True,
                suppression_reason="Outside business hours",
            )

        # Find applicable step based on time
        minutes_elapsed = incident.minutes_since_triggered
        step = policy.get_step_for_time(int(minutes_elapsed))

        if step is None:
            return EscalationResult(
                incident_id=incident.incident_id,
                triggered=False,
                policy_id=policy.id,
            )

        # Check if this step was already executed
        if incident.current_escalation_step >= step.step_number:
            # Check if repeat is enabled
            if not step.repeat:
                return EscalationResult(
                    incident_id=incident.incident_id,
                    triggered=False,
                    policy_id=policy.id,
                    step_number=step.step_number,
                    suppression_reason="Step already executed",
                )

            # Check repeat interval
            if incident.last_escalation_at:
                minutes_since_last = (
                    datetime.utcnow() - incident.last_escalation_at
                ).total_seconds() / 60
                if minutes_since_last < step.repeat_interval_minutes:
                    return EscalationResult(
                        incident_id=incident.incident_id,
                        triggered=False,
                        policy_id=policy.id,
                        step_number=step.step_number,
                        suppression_reason=f"Repeat interval not reached ({int(minutes_since_last)}/{step.repeat_interval_minutes} min)",
                    )

        # Evaluate step conditions
        if step.conditions and not evaluate_conditions(step.conditions, incident):
            return EscalationResult(
                incident_id=incident.incident_id,
                triggered=False,
                policy_id=policy.id,
                step_number=step.step_number,
                suppression_reason="Step conditions not met",
            )

        # Execute step actions
        return await self._execute_step(incident, policy, step)

    async def _execute_step(
        self,
        incident: IncidentState,
        policy: EscalationPolicy,
        step: EscalationStep,
    ) -> EscalationResult:
        """Execute escalation step actions."""
        # Resolve action targets from policy defaults
        actions = self._resolve_action_targets(step.actions, policy, step)

        # Execute actions
        results = await execute_actions(actions, incident)

        # Track results
        executed = [r.action.id for r in results if r.success]
        failed = [r.action.id for r in results if not r.success]
        errors = [r.error for r in results if r.error]

        # Update incident escalation state
        await self.store.update_incident_escalation(
            incident.incident_id,
            step=step.step_number,
            policy_id=policy.id,
        )

        # Record escalation history
        await self.store.record_escalation(
            incident.incident_id,
            step.step_number,
            policy.id,
            executed,
        )

        # Create audit entries
        for result in results:
            await self.store.store_audit_entry(
                result.to_audit_entry(incident.incident_id, policy.id)
            )

        # Emit events
        result = EscalationResult(
            incident_id=incident.incident_id,
            triggered=len(executed) > 0,
            policy_id=policy.id,
            step_number=step.step_number,
            actions_executed=executed,
            actions_failed=failed,
            errors=errors,
        )

        if result.triggered:
            await self._emit("on_escalation", incident, result)

        for action_result in results:
            await self._emit("on_action_executed", incident, action_result)

        logger.info(
            "escalation_step_executed",
            incident_id=incident.incident_id,
            policy_id=policy.id,
            step=step.step_number,
            executed=len(executed),
            failed=len(failed),
        )

        return result

    def _resolve_action_targets(
        self,
        actions: list,
        policy: EscalationPolicy,
        step: EscalationStep,
    ) -> list:
        """Resolve action targets from policy defaults."""
        from .models import ActionType, EscalationAction

        resolved = []
        for action in actions:
            # Create a copy to avoid mutating original
            action_copy = EscalationAction(
                id=action.id,
                action_type=action.action_type,
                target=action.target,
                target_id=action.target_id,
                params=dict(action.params),
                retry_count=action.retry_count,
                retry_delay_seconds=action.retry_delay_seconds,
            )

            # Resolve target from policy defaults if not set
            if not action_copy.target and not action_copy.target_id:
                if action_copy.action_type == ActionType.ESCALATE_TO_MANAGER:
                    action_copy.target = policy.manager
                elif step.step_number == 1:
                    action_copy.target = policy.primary_responder
                elif step.step_number == 2:
                    action_copy.target = policy.secondary_responder
                elif step.step_number >= 3:
                    action_copy.target = policy.manager

            resolved.append(action_copy)

        return resolved

    def _is_business_hours(self, policy: EscalationPolicy) -> bool:
        """Check if current time is within business hours."""
        from zoneinfo import ZoneInfo

        try:
            tz = ZoneInfo(policy.timezone)
            now = datetime.now(tz)
            return policy.business_hours_start <= now.hour < policy.business_hours_end
        except Exception:
            # If timezone fails, assume business hours
            return True

    async def _evaluate_rules(
        self, incident: IncidentState
    ) -> EscalationResult:
        """Evaluate incident against standalone rules."""
        rules, _ = await self.store.list_rules(enabled_only=True)

        for rule in rules:
            if not self._rule_matches(rule, incident):
                continue

            # Evaluate rule conditions
            if not evaluate_conditions(rule.conditions, incident):
                continue

            # Execute rule actions
            results = await execute_actions(rule.actions, incident)

            executed = [r.action.id for r in results if r.success]
            failed = [r.action.id for r in results if not r.success]
            errors = [r.error for r in results if r.error]

            # Create audit entries
            for result in results:
                await self.store.store_audit_entry(
                    result.to_audit_entry(incident.incident_id)
                )

            if executed:
                result = EscalationResult(
                    incident_id=incident.incident_id,
                    triggered=True,
                    rule_id=rule.id,
                    actions_executed=executed,
                    actions_failed=failed,
                    errors=errors,
                )
                await self._emit("on_escalation", incident, result)

                logger.info(
                    "escalation_rule_triggered",
                    incident_id=incident.incident_id,
                    rule_id=rule.id,
                    executed=len(executed),
                )

                return result

        return EscalationResult(
            incident_id=incident.incident_id,
            triggered=False,
        )

    def _rule_matches(self, rule: EscalationRule, incident: IncidentState) -> bool:
        """Check if a rule matches an incident."""
        # Service pattern
        if rule.service_pattern:
            if not re.match(rule.service_pattern, incident.service):
                return False

        # Team filter
        if rule.team_id and rule.team_id != incident.team_id:
            return False

        # Severity filter
        if rule.severity_filter:
            if incident.severity.lower() not in [
                s.lower() for s in rule.severity_filter
            ]:
                return False

        # Tag filters
        for tag_key, tag_value in rule.tag_filters.items():
            incident_value = incident.tags.get(tag_key)
            if incident_value is None or incident_value != tag_value:
                return False

        return True

    # Policy management methods

    async def create_policy(self, policy: EscalationPolicy) -> EscalationPolicy:
        """Create a new escalation policy."""
        policy.created_at = datetime.utcnow()
        policy.updated_at = datetime.utcnow()
        await self.store.store_policy(policy)
        logger.info("escalation_policy_created", policy_id=policy.id, name=policy.name)
        return policy

    async def update_policy(
        self, policy_id: str, updates: dict
    ) -> EscalationPolicy | None:
        """Update an existing policy."""
        policy = await self.store.get_policy(policy_id)
        if not policy:
            return None

        for key, value in updates.items():
            if hasattr(policy, key) and value is not None:
                setattr(policy, key, value)

        policy.updated_at = datetime.utcnow()
        await self.store.store_policy(policy)
        logger.info("escalation_policy_updated", policy_id=policy_id)
        return policy

    async def delete_policy(self, policy_id: str) -> bool:
        """Delete a policy."""
        result = await self.store.delete_policy(policy_id)
        if result:
            logger.info("escalation_policy_deleted", policy_id=policy_id)
        return result

    async def get_policy(self, policy_id: str) -> EscalationPolicy | None:
        """Get a policy by ID."""
        return await self.store.get_policy(policy_id)

    async def list_policies(
        self,
        tenant_id: str | None = None,
        service_id: str | None = None,
        team_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[EscalationPolicy], int]:
        """List policies with filters."""
        return await self.store.list_policies(
            tenant_id=tenant_id,
            service_id=service_id,
            team_id=team_id,
            limit=limit,
            offset=offset,
        )

    # Rule management methods

    async def create_rule(self, rule: EscalationRule) -> EscalationRule:
        """Create a new escalation rule."""
        rule.created_at = datetime.utcnow()
        rule.updated_at = datetime.utcnow()
        await self.store.store_rule(rule)
        logger.info("escalation_rule_created", rule_id=rule.id, name=rule.name)
        return rule

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule."""
        result = await self.store.delete_rule(rule_id)
        if result:
            logger.info("escalation_rule_deleted", rule_id=rule_id)
        return result

    async def list_rules(
        self, enabled_only: bool = True, limit: int = 100, offset: int = 0
    ) -> tuple[list[EscalationRule], int]:
        """List rules."""
        return await self.store.list_rules(
            enabled_only=enabled_only, limit=limit, offset=offset
        )

    # Maintenance window management

    async def create_maintenance_window(
        self, window: MaintenanceWindow
    ) -> MaintenanceWindow:
        """Create a maintenance window."""
        await self.store.store_maintenance_window(window)
        logger.info(
            "maintenance_window_created",
            window_id=window.id,
            name=window.name,
            start=window.start_time.isoformat(),
            end=window.end_time.isoformat(),
        )
        return window

    async def delete_maintenance_window(self, window_id: str) -> bool:
        """Delete a maintenance window."""
        result = await self.store.delete_maintenance_window(window_id)
        if result:
            logger.info("maintenance_window_deleted", window_id=window_id)
        return result

    # Audit log

    async def get_audit_log(
        self,
        incident_id: str | None = None,
        policy_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[EscalationAuditEntry], int]:
        """Get escalation audit log."""
        return await self.store.get_audit_log(
            incident_id=incident_id,
            policy_id=policy_id,
            limit=limit,
            offset=offset,
        )

    async def get_stats(self) -> dict:
        """Get engine statistics."""
        policies, policy_count = await self.store.list_policies()
        rules, rule_count = await self.store.list_rules(enabled_only=False)
        incidents = await self.store.list_active_incidents()

        return {
            "initialized": self._initialized,
            "policies_count": policy_count,
            "rules_count": rule_count,
            "active_incidents": len(incidents),
        }


# Global engine instance
_engine_instance: EscalationEngine | None = None


async def get_escalation_engine(settings: Any = None) -> EscalationEngine:
    """Get or create the global escalation engine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = EscalationEngine(settings=settings)
        await _engine_instance.initialize()
    return _engine_instance


async def shutdown_escalation_engine() -> None:
    """Shutdown the global escalation engine."""
    global _engine_instance
    if _engine_instance:
        await _engine_instance.close()
        _engine_instance = None
