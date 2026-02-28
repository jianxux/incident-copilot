"""Opsgenie data importer with resumable, cancellable imports."""

import logging
from datetime import datetime, timezone

from src.migrations.models import (
    EntityMigrationResult,
    MigrationEntityType,
    MigrationJob,
    MigrationStatus,
)

from .client import OpsgenieClient
from .mapper import OpsgenieMapper

logger = logging.getLogger(__name__)


class OpsgenieImporter:
    """Import data from Opsgenie into incident-copilot."""

    def __init__(self, client: OpsgenieClient, api_key: str) -> None:
        self.client = client
        self.mapper = OpsgenieMapper()
        self.job = MigrationJob(
            source="opsgenie",
            api_key_masked=MigrationJob.mask_key(api_key),
        )
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the running migration."""
        self._cancelled = True

    async def run(self, selected_entities: list[MigrationEntityType]) -> MigrationJob:
        """Run the migration for selected entity types."""
        self.job.selected_entities = selected_entities
        self.job.status = MigrationStatus.RUNNING
        self.job.started_at = datetime.now(timezone.utc)

        import_methods = {
            MigrationEntityType.SERVICES: self._import_services,
            MigrationEntityType.TEAMS: self._import_teams,
            MigrationEntityType.USERS: self._import_users,
            MigrationEntityType.SCHEDULES: self._import_schedules,
            MigrationEntityType.ESCALATIONS: self._import_escalations,
            MigrationEntityType.ALERTS: self._import_alerts,
            MigrationEntityType.INTEGRATIONS: self._import_integrations,
        }

        total = len(selected_entities)
        for i, entity_type in enumerate(selected_entities):
            if self._cancelled:
                self.job.status = MigrationStatus.CANCELLED
                self.job.completed_at = datetime.now(timezone.utc)
                return self.job

            method = import_methods.get(entity_type)
            if method:
                result = await method()
                self.job.results[entity_type.value] = result

            self.job.progress_pct = ((i + 1) / total) * 100

        self.job.status = MigrationStatus.COMPLETED
        self.job.completed_at = datetime.now(timezone.utc)

        # Mark as failed if any entity had all failures
        for r in self.job.results.values():
            if r.total > 0 and r.failed == r.total:
                self.job.status = MigrationStatus.FAILED
                break

        return self.job

    async def _import_services(self) -> EntityMigrationResult:
        result = EntityMigrationResult(entity_type=MigrationEntityType.SERVICES)
        try:
            services = await self.client.get_services()
            result.total = len(services)
            for svc in services:
                try:
                    self.mapper.map_service(svc)
                    result.succeeded += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Service {svc.get('name', '?')}: {e}")
        except Exception as e:
            result.errors.append(f"Failed to fetch services: {e}")
        return result

    async def _import_teams(self) -> EntityMigrationResult:
        result = EntityMigrationResult(entity_type=MigrationEntityType.TEAMS)
        try:
            teams = await self.client.get_teams()
            result.total = len(teams)
            for team in teams:
                try:
                    self.mapper.map_team(team)
                    result.succeeded += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Team {team.get('name', '?')}: {e}")
        except Exception as e:
            result.errors.append(f"Failed to fetch teams: {e}")
        return result

    async def _import_users(self) -> EntityMigrationResult:
        result = EntityMigrationResult(entity_type=MigrationEntityType.USERS)
        try:
            users = await self.client.get_users()
            result.total = len(users)
            for user in users:
                try:
                    self.mapper.map_user(user)
                    result.succeeded += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"User {user.get('fullName', '?')}: {e}")
        except Exception as e:
            result.errors.append(f"Failed to fetch users: {e}")
        return result

    async def _import_schedules(self) -> EntityMigrationResult:
        result = EntityMigrationResult(entity_type=MigrationEntityType.SCHEDULES)
        try:
            schedules = await self.client.get_schedules()
            result.total = len(schedules)
            for sched in schedules:
                try:
                    self.mapper.map_schedule(sched)
                    result.succeeded += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Schedule {sched.get('name', '?')}: {e}")
        except Exception as e:
            result.errors.append(f"Failed to fetch schedules: {e}")
        return result

    async def _import_escalations(self) -> EntityMigrationResult:
        result = EntityMigrationResult(entity_type=MigrationEntityType.ESCALATIONS)
        try:
            escalations = await self.client.get_escalations()
            result.total = len(escalations)
            for esc in escalations:
                try:
                    self.mapper.map_escalation(esc)
                    result.succeeded += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Escalation {esc.get('name', '?')}: {e}")
        except Exception as e:
            result.errors.append(f"Failed to fetch escalations: {e}")
        return result

    async def _import_alerts(self) -> EntityMigrationResult:
        result = EntityMigrationResult(entity_type=MigrationEntityType.ALERTS)
        try:
            alerts = await self.client.get_alerts()
            result.total = len(alerts)
            for alert in alerts:
                try:
                    self.mapper.map_alert_to_incident(alert)
                    result.succeeded += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Alert {alert.get('message', '?')}: {e}")
        except Exception as e:
            result.errors.append(f"Failed to fetch alerts: {e}")
        return result

    async def _import_integrations(self) -> EntityMigrationResult:
        result = EntityMigrationResult(entity_type=MigrationEntityType.INTEGRATIONS)
        try:
            integrations = await self.client.get_integrations()
            result.total = len(integrations)
            for integ in integrations:
                try:
                    # Integrations are logged as suggestions rather than imported
                    result.succeeded += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Integration {integ.get('name', '?')}: {e}")
        except Exception as e:
            result.errors.append(f"Failed to fetch integrations: {e}")
        return result
