"""Tests for the Opsgenie migration module."""

from unittest.mock import AsyncMock, patch

import pytest

from src.migrations.models import (
    MigrationEntityType,
    MigrationJob,
    MigrationStatus,
)
from src.migrations.opsgenie.client import OpsgenieClient
from src.migrations.opsgenie.importer import OpsgenieImporter
from src.migrations.opsgenie.mapper import OpsgenieMapper
from src.migrations.opsgenie.validator import OpsgenieValidator

# --- Mapper Tests ---


class TestOpsgenieMapper:
    def test_map_severity(self):
        assert OpsgenieMapper.map_severity("P1").value == "critical"
        assert OpsgenieMapper.map_severity("P2").value == "high"
        assert OpsgenieMapper.map_severity("P3").value == "medium"
        assert OpsgenieMapper.map_severity("P4").value == "low"
        assert OpsgenieMapper.map_severity("P5").value == "info"
        assert OpsgenieMapper.map_severity("unknown").value == "medium"

    def test_map_alert_status(self):
        assert OpsgenieMapper.map_alert_status("open") == "triggered"
        assert OpsgenieMapper.map_alert_status("closed") == "resolved"
        assert OpsgenieMapper.map_alert_status("acked") == "acknowledged"
        assert OpsgenieMapper.map_alert_status("weird") == "triggered"

    def test_map_service(self):
        og = {
            "id": "svc-1",
            "name": "payments",
            "description": "Pay svc",
            "tags": ["prod"],
        }
        svc = OpsgenieMapper.map_service(og)
        assert svc.name == "payments"
        assert svc.description == "Pay svc"
        assert "prod" in svc.tags
        assert svc.metadata["source"] == "opsgenie"

    def test_map_team(self):
        og = {
            "id": "t1",
            "name": "Platform",
            "description": "Infra team",
            "members": [{"user": {"id": "u1"}, "role": "admin"}],
        }
        team = OpsgenieMapper.map_team(og)
        assert team["name"] == "Platform"
        assert len(team["members"]) == 1

    def test_map_user(self):
        og = {
            "id": "u1",
            "fullName": "Alice",
            "username": "alice@co.com",
            "role": {"name": "admin"},
        }
        user = OpsgenieMapper.map_user(og)
        assert user["name"] == "Alice"
        assert user["email"] == "alice@co.com"

    def test_map_schedule(self):
        og = {
            "id": "s1",
            "name": "Primary",
            "timezone": "US/Pacific",
            "ownerTeam": {"name": "Platform"},
        }
        sched = OpsgenieMapper.map_schedule(og)
        assert sched["name"] == "Primary"
        assert sched["timezone"] == "US/Pacific"

    def test_map_escalation(self):
        og = {
            "id": "e1",
            "name": "Default",
            "rules": [
                {
                    "delay": {"timeAmount": 5},
                    "recipient": {"type": "team"},
                    "condition": "if-not-acked",
                }
            ],
        }
        esc = OpsgenieMapper.map_escalation(og)
        assert esc["name"] == "Default"
        assert esc["rules"][0]["delay_minutes"] == 5

    def test_map_alert_to_incident(self):
        og = {
            "id": "a1",
            "message": "High CPU",
            "description": "CPU > 90%",
            "priority": "P1",
            "status": "closed",
            "tags": ["infra"],
            "createdAt": "2024-01-01T00:00:00Z",
        }
        inc = OpsgenieMapper.map_alert_to_incident(og)
        assert inc["title"] == "High CPU"
        assert inc["severity"] == "critical"
        assert inc["status"] == "resolved"


# --- Model Tests ---


class TestMigrationModels:
    def test_mask_key(self):
        assert MigrationJob.mask_key("abcdefghijklmn") == "abcd****klmn"
        assert MigrationJob.mask_key("short") == "****"

    def test_job_defaults(self):
        job = MigrationJob()
        assert job.status == MigrationStatus.PENDING
        assert job.progress_pct == 0.0
        assert job.source == "opsgenie"


# --- Client Tests ---


@pytest.mark.asyncio
class TestOpsgenieClient:
    async def test_validate_api_key_success(self):
        client = OpsgenieClient(api_key="test-key")
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"name": "Test Account"}}
        mock_resp.raise_for_status = lambda: None

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_resp)
            mock_get.return_value = mock_http
            assert await client.validate_api_key() is True

    async def test_get_services(self):
        client = OpsgenieClient(api_key="test-key")
        page_data = {"data": [{"id": "s1", "name": "svc1"}], "paging": {}}

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = page_data
            services = await client.get_services()
            assert len(services) == 1
            assert services[0]["name"] == "svc1"


# --- Validator Tests ---


@pytest.mark.asyncio
class TestOpsgenieValidator:
    async def test_validate_connection_success(self):
        mock_client = AsyncMock(spec=OpsgenieClient)
        mock_client.validate_api_key.return_value = True
        validator = OpsgenieValidator(mock_client)
        valid, msg = await validator.validate_connection()
        assert valid is True

    async def test_validate_connection_failure(self):
        mock_client = AsyncMock(spec=OpsgenieClient)
        mock_client.validate_api_key.return_value = False
        validator = OpsgenieValidator(mock_client)
        valid, msg = await validator.validate_connection()
        assert valid is False


# --- Importer Tests ---


@pytest.mark.asyncio
class TestOpsgenieImporter:
    async def test_run_success(self):
        mock_client = AsyncMock(spec=OpsgenieClient)
        mock_client.get_services.return_value = [
            {"id": "s1", "name": "svc1"},
            {"id": "s2", "name": "svc2"},
        ]
        mock_client.get_teams.return_value = [{"id": "t1", "name": "Team A"}]

        importer = OpsgenieImporter(mock_client, api_key="test-key-12345678")
        job = await importer.run(
            [MigrationEntityType.SERVICES, MigrationEntityType.TEAMS]
        )

        assert job.status == MigrationStatus.COMPLETED
        assert job.progress_pct == 100.0
        assert job.results["services"].succeeded == 2
        assert job.results["teams"].succeeded == 1

    async def test_cancel(self):
        mock_client = AsyncMock(spec=OpsgenieClient)
        mock_client.get_services.return_value = [{"id": "s1", "name": "svc1"}]

        importer = OpsgenieImporter(mock_client, api_key="test-key-12345678")
        importer.cancel()
        job = await importer.run([MigrationEntityType.SERVICES])
        assert job.status == MigrationStatus.CANCELLED


# --- Route Tests ---


@pytest.mark.asyncio
class TestMigrationRoutes:
    async def test_history_empty(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from src.migrations.routes import _jobs, router

        _jobs.clear()

        app = FastAPI()
        app.include_router(router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/migrations/history")
            assert resp.status_code == 200
            assert resp.json() == []

    async def test_status_not_found(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from src.migrations.routes import _jobs, router

        _jobs.clear()

        app = FastAPI()
        app.include_router(router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/migrations/nonexistent/status")
            assert resp.status_code == 404
