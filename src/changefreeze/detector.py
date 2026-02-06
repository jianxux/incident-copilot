"""Deployment detection during change freezes from GitHub webhooks."""

import uuid
from datetime import datetime

import structlog

from .models import (
    ChangeFreeze,
    DeploymentEvent,
    FreezeException,
    FreezeViolation,
    ViolationSeverity,
)
from .store import ChangeFreezeStore, changefreeze_store

logger = structlog.get_logger()


class DeploymentDetector:
    """
    Detects deployments from GitHub webhooks and checks against active freezes.
    
    Supports:
    - GitHub deployment events
    - GitHub deployment_status events
    - GitHub push events (for branches matching deploy patterns)
    - GitHub release events
    """

    def __init__(self, store: ChangeFreezeStore | None = None):
        self.store = store or changefreeze_store
        self._deploy_branch_patterns = [
            "main",
            "master",
            "release",
            "production",
            "prod",
        ]

    async def process_github_webhook(
        self,
        event_type: str,
        payload: dict,
    ) -> DeploymentEvent | None:
        """
        Process a GitHub webhook event and detect deployments.
        
        Args:
            event_type: GitHub event type (deployment, deployment_status, push, release)
            payload: GitHub webhook payload
            
        Returns:
            DeploymentEvent if a deployment was detected, None otherwise
        """
        logger.info(
            "processing_github_webhook",
            event_type=event_type,
            repository=payload.get("repository", {}).get("full_name"),
        )

        deployment_event = None

        if event_type == "deployment":
            deployment_event = await self._process_deployment_event(payload)
        elif event_type == "deployment_status":
            deployment_event = await self._process_deployment_status_event(payload)
        elif event_type == "push":
            deployment_event = await self._process_push_event(payload)
        elif event_type == "release":
            deployment_event = await self._process_release_event(payload)
        else:
            logger.debug("ignoring_event_type", event_type=event_type)
            return None

        if deployment_event:
            # Check against active freezes
            deployment_event = await self._check_against_freezes(deployment_event)
            
            # Save the event
            await self.store.save_deployment(deployment_event)
            
            logger.info(
                "deployment_detected",
                event_id=deployment_event.event_id,
                service=deployment_event.service_name,
                environment=deployment_event.environment,
                during_freeze=deployment_event.during_freeze,
                is_violation=deployment_event.is_violation,
            )

        return deployment_event

    async def _process_deployment_event(self, payload: dict) -> DeploymentEvent | None:
        """Process GitHub deployment event."""
        deployment = payload.get("deployment", {})
        repository = payload.get("repository", {})
        sender = payload.get("sender", {})

        environment = deployment.get("environment", "production")
        
        # Extract service name from repository or deployment payload
        service_name = deployment.get("payload", {}).get(
            "service_name",
            repository.get("name", "unknown"),
        )

        return DeploymentEvent(
            event_id=str(uuid.uuid4()),
            source="github",
            source_event_id=str(deployment.get("id")),
            service_name=service_name,
            repository=repository.get("full_name", ""),
            environment=environment,
            commit_sha=deployment.get("sha"),
            branch=deployment.get("ref"),
            deployed_by=sender.get("login", "unknown"),
            deployed_at=datetime.utcnow(),
            metadata={
                "task": deployment.get("task"),
                "description": deployment.get("description"),
                "creator": deployment.get("creator", {}).get("login"),
            },
        )

    async def _process_deployment_status_event(
        self, payload: dict
    ) -> DeploymentEvent | None:
        """Process GitHub deployment_status event."""
        deployment_status = payload.get("deployment_status", {})
        deployment = payload.get("deployment", {})
        repository = payload.get("repository", {})
        sender = payload.get("sender", {})

        # Only process successful deployments
        state = deployment_status.get("state")
        if state not in ("success", "inactive"):
            logger.debug(
                "ignoring_deployment_status",
                state=state,
                description=deployment_status.get("description"),
            )
            return None

        environment = deployment_status.get("environment") or deployment.get(
            "environment", "production"
        )
        
        service_name = deployment.get("payload", {}).get(
            "service_name",
            repository.get("name", "unknown"),
        )

        return DeploymentEvent(
            event_id=str(uuid.uuid4()),
            source="github",
            source_event_id=str(deployment_status.get("id")),
            service_name=service_name,
            repository=repository.get("full_name", ""),
            environment=environment,
            commit_sha=deployment.get("sha"),
            branch=deployment.get("ref"),
            deployed_by=sender.get("login", "unknown"),
            deployed_at=datetime.utcnow(),
            metadata={
                "state": state,
                "description": deployment_status.get("description"),
                "log_url": deployment_status.get("log_url"),
                "target_url": deployment_status.get("target_url"),
            },
        )

    async def _process_push_event(self, payload: dict) -> DeploymentEvent | None:
        """Process GitHub push event (for deploy branches)."""
        ref = payload.get("ref", "")
        repository = payload.get("repository", {})
        pusher = payload.get("pusher", {})
        head_commit = payload.get("head_commit", {})

        # Extract branch name
        branch = ref.replace("refs/heads/", "")

        # Only consider pushes to deploy branches as deployments
        if not any(pattern in branch.lower() for pattern in self._deploy_branch_patterns):
            return None

        # Determine environment from branch
        environment = "production"
        if "staging" in branch.lower():
            environment = "staging"
        elif "dev" in branch.lower():
            environment = "development"

        return DeploymentEvent(
            event_id=str(uuid.uuid4()),
            source="github",
            source_event_id=payload.get("after"),  # Use commit SHA as event ID
            service_name=repository.get("name", "unknown"),
            repository=repository.get("full_name", ""),
            environment=environment,
            commit_sha=payload.get("after"),
            commit_message=head_commit.get("message"),
            branch=branch,
            deployed_by=pusher.get("name", "unknown"),
            deployed_at=datetime.utcnow(),
            metadata={
                "before": payload.get("before"),
                "forced": payload.get("forced"),
                "commits_count": len(payload.get("commits", [])),
            },
        )

    async def _process_release_event(self, payload: dict) -> DeploymentEvent | None:
        """Process GitHub release event."""
        action = payload.get("action")
        release = payload.get("release", {})
        repository = payload.get("repository", {})
        sender = payload.get("sender", {})

        # Only process published releases
        if action != "published":
            return None

        return DeploymentEvent(
            event_id=str(uuid.uuid4()),
            source="github",
            source_event_id=str(release.get("id")),
            service_name=repository.get("name", "unknown"),
            repository=repository.get("full_name", ""),
            environment="production",  # Releases typically go to production
            commit_sha=release.get("target_commitish"),
            tag=release.get("tag_name"),
            deployed_by=sender.get("login", "unknown"),
            deployed_at=datetime.utcnow(),
            metadata={
                "release_name": release.get("name"),
                "prerelease": release.get("prerelease"),
                "draft": release.get("draft"),
                "html_url": release.get("html_url"),
            },
        )

    async def _check_against_freezes(
        self, event: DeploymentEvent
    ) -> DeploymentEvent:
        """Check deployment event against active freezes."""
        is_frozen, active_freezes, valid_exceptions = await self.store.check_freeze_status(
            service_name=event.service_name,
            environment=event.environment,
            at_time=event.deployed_at,
        )

        if not is_frozen:
            return event

        # Deployment is during a freeze
        event.during_freeze = True
        
        # Use the first active freeze (most relevant)
        freeze = active_freezes[0]
        event.freeze_id = freeze.freeze_id

        # Check for valid exceptions
        if valid_exceptions:
            exception = valid_exceptions[0]
            event.exception_id = exception.exception_id
            event.is_violation = False
            
            # Mark exception as used
            exception.deployment_event_ids.append(event.event_id)
            exception.deployment_completed = True
            exception.deployment_completed_at = datetime.utcnow()
            await self.store.save_exception(exception)
            
            logger.info(
                "deployment_with_exception",
                event_id=event.event_id,
                exception_id=exception.exception_id,
                is_emergency=exception.is_emergency,
            )
        else:
            # This is a violation!
            event.is_violation = True
            violation = await self._create_violation(event, freeze)
            event.violation_id = violation.violation_id
            
            logger.warning(
                "freeze_violation_detected",
                event_id=event.event_id,
                violation_id=violation.violation_id,
                freeze_id=freeze.freeze_id,
                service=event.service_name,
                deployed_by=event.deployed_by,
            )

        return event

    async def _create_violation(
        self,
        event: DeploymentEvent,
        freeze: ChangeFreeze,
    ) -> FreezeViolation:
        """Create a violation record for an unauthorized deployment."""
        # Determine severity based on environment and scope
        severity = ViolationSeverity.HIGH
        if event.environment.lower() in ("staging", "stage"):
            severity = ViolationSeverity.MEDIUM
        elif event.environment.lower() in ("development", "dev", "test"):
            severity = ViolationSeverity.LOW
        elif freeze.scope.value == "global":
            severity = ViolationSeverity.CRITICAL

        violation = FreezeViolation(
            violation_id=str(uuid.uuid4()),
            freeze_id=freeze.freeze_id,
            deployment_event_id=event.event_id,
            service_name=event.service_name,
            environment=event.environment,
            repository=event.repository,
            deployed_by=event.deployed_by,
            deployed_at=event.deployed_at,
            severity=severity,
            freeze_name=freeze.name,
            commit_sha=event.commit_sha,
            commit_message=event.commit_message,
        )

        await self.store.save_violation(violation)
        return violation

    async def check_deployment_allowed(
        self,
        service_name: str,
        environment: str = "production",
    ) -> tuple[bool, str, list[ChangeFreeze], list[FreezeException]]:
        """
        Check if a deployment is allowed for a service.
        
        Returns:
            Tuple of (allowed, reason, active_freezes, valid_exceptions)
        """
        is_frozen, active_freezes, valid_exceptions = await self.store.check_freeze_status(
            service_name=service_name,
            environment=environment,
        )

        if not is_frozen:
            return (True, "No active change freeze", [], [])

        if valid_exceptions:
            exception = valid_exceptions[0]
            reason = f"Approved exception: {exception.reason}"
            if exception.is_emergency:
                reason = f"Emergency deployment: {exception.emergency_ticket_id or exception.reason}"
            return (True, reason, active_freezes, valid_exceptions)

        freeze = active_freezes[0]
        reason = f"Change freeze active: {freeze.name} (until {freeze.ends_at.isoformat()})"
        return (False, reason, active_freezes, [])


# Global detector instance
deployment_detector = DeploymentDetector()
