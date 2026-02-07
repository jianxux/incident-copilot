"""
Escalation Service - Core business logic for escalation management.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from .models import (
    EscalationPolicy,
    EscalationLevel,
    EscalationState,
    EscalationStatus,
    EscalationHistoryEntry,
    OnCallAssignment,
    TeamRotation,
    Severity,
    TriggerEscalationRequest,
    OverrideEscalationRequest,
)


class EscalationService:
    """Service for managing escalation policies and state."""

    def __init__(self):
        # In-memory storage (replace with database in production)
        self._policies: dict[UUID, EscalationPolicy] = {}
        self._states: dict[str, EscalationState] = {}  # incident_id -> state
        self._oncall: dict[str, OnCallAssignment] = {}  # team_id -> current oncall
        self._rotations: dict[str, TeamRotation] = {}  # team_id -> rotation
        self._history: list[EscalationHistoryEntry] = []

    async def create_policy(self, policy: EscalationPolicy) -> EscalationPolicy:
        """Create a new escalation policy."""
        self._policies[policy.id] = policy
        return policy

    async def get_policy(self, policy_id: UUID) -> EscalationPolicy | None:
        """Get a policy by ID."""
        return self._policies.get(policy_id)

    async def list_policies(
        self,
        enabled_only: bool = False,
        service: str | None = None,
        severity: Severity | None = None,
        tags: list[str] | None = None,
    ) -> list[EscalationPolicy]:
        """List policies with optional filters."""
        policies = list(self._policies.values())

        if enabled_only:
            policies = [p for p in policies if p.enabled]
        if service:
            policies = [p for p in policies if not p.services or service in p.services]
        if severity:
            policies = [
                p for p in policies if not p.severities or severity in p.severities
            ]
        if tags:
            policies = [p for p in policies if any(t in p.tags for t in tags)]

        return sorted(policies, key=lambda p: -p.priority)

    async def update_policy(
        self, policy_id: UUID, updates: dict[str, Any]
    ) -> EscalationPolicy | None:
        """Update an existing policy."""
        policy = self._policies.get(policy_id)
        if not policy:
            return None

        updated_data = policy.model_dump()
        for key, value in updates.items():
            if value is not None:
                updated_data[key] = value
        updated_data["updated_at"] = datetime.utcnow()

        updated_policy = EscalationPolicy(**updated_data)
        self._policies[policy_id] = updated_policy
        return updated_policy

    async def delete_policy(self, policy_id: UUID) -> bool:
        """Delete a policy."""
        if policy_id in self._policies:
            del self._policies[policy_id]
            return True
        return False

    async def find_matching_policy(
        self, incident_context: dict[str, Any]
    ) -> EscalationPolicy | None:
        """Find the best matching policy for an incident."""
        service = incident_context.get("service")
        severity = incident_context.get("severity")

        policies = await self.list_policies(
            enabled_only=True,
            service=service,
            severity=Severity(severity) if severity else None,
        )

        for policy in policies:
            if self._matches_conditions(policy, incident_context):
                return policy

        return policies[0] if policies else None

    def _matches_conditions(
        self, policy: EscalationPolicy, context: dict[str, Any]
    ) -> bool:
        """Check if all policy conditions match."""
        if not policy.conditions:
            return True
        return all(cond.matches(context) for cond in policy.conditions)

    async def get_escalation_state(self, incident_id: str) -> EscalationState | None:
        """Get current escalation state for an incident."""
        return self._states.get(incident_id)

    async def start_escalation(
        self,
        incident_id: str,
        policy: EscalationPolicy,
        context: dict[str, Any] | None = None,
    ) -> EscalationState:
        """Start escalation for an incident."""
        if incident_id in self._states:
            return self._states[incident_id]

        first_level = policy.levels[0] if policy.levels else None
        next_escalation = None
        if first_level:
            next_escalation = datetime.utcnow() + timedelta(
                minutes=first_level.delay_minutes
            )

        state = EscalationState(
            incident_id=incident_id,
            policy_id=policy.id,
            current_level=1,
            status=EscalationStatus.PENDING,
            next_escalation_at=next_escalation,
        )
        self._states[incident_id] = state
        return state

    async def escalate(
        self, incident_id: str, request: TriggerEscalationRequest | None = None
    ) -> EscalationState | None:
        """Escalate an incident to the next level."""
        state = self._states.get(incident_id)
        if not state:
            return None

        policy = self._policies.get(state.policy_id)
        if not policy:
            return None

        target_level = request.target_level if request else None
        next_level = target_level or state.current_level + 1

        # Find the level configuration
        level_config = self._get_level(policy, next_level)
        if not level_config:
            # Check for repeat
            if policy.repeat_enabled and state.repeat_count < policy.max_repeats:
                state.repeat_count += 1
                next_level = 1
                level_config = self._get_level(policy, 1)

        if not level_config:
            state.status = EscalationStatus.RESOLVED
            return state

        # Record history
        history_entry = EscalationHistoryEntry(
            incident_id=incident_id,
            policy_id=policy.id,
            policy_name=policy.name,
            level=next_level,
            level_name=level_config.name,
            status=EscalationStatus.TRIGGERED,
            triggered_at=datetime.utcnow(),
            metadata={"reason": request.reason if request else "auto"},
        )
        state.history.append(history_entry)
        self._history.append(history_entry)

        # Update state
        state.current_level = next_level
        state.status = EscalationStatus.TRIGGERED
        state.last_escalation_at = datetime.utcnow()

        # Calculate next escalation
        next_level_config = self._get_level(policy, next_level + 1)
        if next_level_config:
            state.next_escalation_at = datetime.utcnow() + timedelta(
                minutes=next_level_config.delay_minutes
            )
        else:
            state.next_escalation_at = None

        return state

    async def get_next_level(
        self, incident_id: str
    ) -> tuple[EscalationLevel | None, int | None]:
        """Get the next escalation level for an incident."""
        state = self._states.get(incident_id)
        if not state:
            return None, None

        policy = self._policies.get(state.policy_id)
        if not policy:
            return None, None

        next_level_num = state.current_level + 1
        level = self._get_level(policy, next_level_num)

        if not level and policy.repeat_enabled:
            if state.repeat_count < policy.max_repeats:
                return self._get_level(policy, 1), 1

        return level, next_level_num if level else None

    def _get_level(
        self, policy: EscalationPolicy, level_num: int
    ) -> EscalationLevel | None:
        """Get a specific level from a policy."""
        for level in policy.levels:
            if level.level == level_num:
                return level
        return None

    async def acknowledge(
        self, incident_id: str, acknowledged_by: str
    ) -> EscalationState | None:
        """Acknowledge an escalation."""
        state = self._states.get(incident_id)
        if not state:
            return None

        state.status = EscalationStatus.ACKNOWLEDGED

        # Update latest history entry
        if state.history:
            state.history[-1].status = EscalationStatus.ACKNOWLEDGED
            state.history[-1].acknowledged_at = datetime.utcnow()
            state.history[-1].acknowledged_by = acknowledged_by

        return state

    async def resolve(
        self, incident_id: str, resolved_by: str
    ) -> EscalationState | None:
        """Resolve an escalation."""
        state = self._states.get(incident_id)
        if not state:
            return None

        state.status = EscalationStatus.RESOLVED

        # Update latest history entry
        if state.history:
            state.history[-1].status = EscalationStatus.RESOLVED
            state.history[-1].resolved_at = datetime.utcnow()
            state.history[-1].resolved_by = resolved_by

        return state

    async def override_escalation(
        self, request: OverrideEscalationRequest
    ) -> EscalationState | None:
        """Override or skip escalation."""
        state = self._states.get(request.incident_id)
        if not state:
            return None

        if request.action == "skip":
            state.status = EscalationStatus.SKIPPED
            if state.history:
                state.history[-1].status = EscalationStatus.SKIPPED
                state.history[-1].skipped_reason = request.reason
        elif request.action == "pause":
            state.is_paused = True
            state.paused_until = request.pause_until
        elif request.action == "resume":
            state.is_paused = False
            state.paused_until = None
        elif request.action == "override":
            state.status = EscalationStatus.OVERRIDDEN
            if request.target_level:
                state.current_level = request.target_level
            if state.history:
                state.history[-1].status = EscalationStatus.OVERRIDDEN
                state.history[-1].override_reason = request.reason

        return state

    async def check_deescalation(
        self, incident_id: str, context: dict[str, Any]
    ) -> EscalationState | None:
        """Check and apply de-escalation rules."""
        state = self._states.get(incident_id)
        if not state:
            return None

        policy = self._policies.get(state.policy_id)
        if not policy or not policy.deescalation_rules:
            return state

        for rule in policy.deescalation_rules:
            if all(cond.matches(context) for cond in rule.conditions):
                if state.current_level > rule.target_level:
                    state.current_level = rule.target_level
                    # Recalculate next escalation with cooldown
                    state.next_escalation_at = datetime.utcnow() + timedelta(
                        minutes=rule.cooldown_minutes
                    )
                break

        return state

    # On-call management
    async def set_oncall(
        self, team_id: str, assignment: OnCallAssignment
    ) -> OnCallAssignment:
        """Set the current on-call for a team."""
        self._oncall[team_id] = assignment
        return assignment

    async def get_oncall(self, team_id: str) -> OnCallAssignment | None:
        """Get the current on-call for a team."""
        return self._oncall.get(team_id)

    async def set_rotation(self, rotation: TeamRotation) -> TeamRotation:
        """Set up a team rotation."""
        self._rotations[rotation.team_id] = rotation
        return rotation

    async def rotate_oncall(self, team_id: str) -> OnCallAssignment | None:
        """Rotate to the next on-call person."""
        rotation = self._rotations.get(team_id)
        if not rotation or not rotation.members:
            return None

        rotation.current_index = (rotation.current_index + 1) % len(rotation.members)
        rotation.last_rotation = datetime.utcnow()

        new_oncall = rotation.members[rotation.current_index]
        self._oncall[team_id] = new_oncall
        return new_oncall

    # History
    async def get_history(
        self,
        incident_id: str | None = None,
        policy_id: UUID | None = None,
        status: EscalationStatus | None = None,
        level: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EscalationHistoryEntry]:
        """Query escalation history with filters."""
        results = self._history

        if incident_id:
            results = [h for h in results if h.incident_id == incident_id]
        if policy_id:
            results = [h for h in results if h.policy_id == policy_id]
        if status:
            results = [h for h in results if h.status == status]
        if level:
            results = [h for h in results if h.level == level]
        if start_date:
            results = [h for h in results if h.triggered_at >= start_date]
        if end_date:
            results = [h for h in results if h.triggered_at <= end_date]

        return results[offset : offset + limit]

    async def get_pending_escalations(self) -> list[EscalationState]:
        """Get all pending escalations that need action."""
        now = datetime.utcnow()
        pending = []

        for state in self._states.values():
            if state.is_paused:
                if state.paused_until and state.paused_until <= now:
                    state.is_paused = False
                else:
                    continue

            if state.status in (EscalationStatus.PENDING, EscalationStatus.TRIGGERED):
                if state.next_escalation_at and state.next_escalation_at <= now:
                    pending.append(state)

        return pending


# Global service instance
_service: EscalationService | None = None


def get_escalation_service() -> EscalationService:
    """Get or create the global escalation service."""
    global _service
    if _service is None:
        _service = EscalationService()
    return _service
