from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.integrations.github import GitHubAdapter, resolve_github_creds


class _FakeTableQuery:
    def __init__(self, data: list[dict]):
        self._data = data

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data)


class _FakeClient:
    def __init__(self, data: list[dict]):
        self._data = data

    def table(self, _name: str):
        return _FakeTableQuery(self._data)


class _FakeDB:
    def __init__(self, data: list[dict]):
        self.client = _FakeClient(data)

    async def _to_thread(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


@pytest.mark.asyncio
async def test_resolve_github_creds_from_env(monkeypatch):
    settings = SimpleNamespace(github_token="env-token", github_org="env-org")
    monkeypatch.setattr("src.integrations.github.get_settings", lambda: settings)

    def _unexpected_db(*_args, **_kwargs):
        raise AssertionError("get_db should not be called when env token is set")

    monkeypatch.setattr("src.integrations.github.get_db", _unexpected_db)

    token, org = await resolve_github_creds("tenant-1")

    assert token == "env-token"
    assert org == "env-org"


@pytest.mark.asyncio
async def test_resolve_github_creds_from_db(monkeypatch):
    settings = SimpleNamespace(github_token="", github_org="")
    monkeypatch.setattr("src.integrations.github.get_settings", lambda: settings)
    monkeypatch.setattr("src.integrations.github.is_supabase_db_enabled", lambda: True)
    monkeypatch.setattr(
        "src.integrations.github.get_db",
        lambda use_admin=True: _FakeDB(
            [{"config": {"encrypted": "encrypted-payload"}}]
        ),
    )
    monkeypatch.setattr(
        "src.integrations.github.decrypt_json",
        lambda _encrypted: {"token": "db-token", "org": "db-org"},
    )

    token, org = await resolve_github_creds("tenant-1")

    assert token == "db-token"
    assert org == "db-org"


@pytest.mark.asyncio
async def test_resolve_github_creds_db_error(monkeypatch):
    settings = SimpleNamespace(github_token="", github_org="")
    monkeypatch.setattr("src.integrations.github.get_settings", lambda: settings)
    monkeypatch.setattr("src.integrations.github.is_supabase_db_enabled", lambda: True)

    class _FailingDB:
        client = SimpleNamespace(table=lambda _name: None)

        async def _to_thread(self, fn, *args, **kwargs):
            raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "src.integrations.github.get_db", lambda use_admin=True: _FailingDB()
    )

    token, org = await resolve_github_creds("tenant-1")

    assert token == ""
    assert org == ""


@pytest.mark.asyncio
async def test_try_ondemand_enrichment_uses_db_creds(monkeypatch):
    from src.api import incidents

    settings = SimpleNamespace(service_repo_map={})
    monkeypatch.setattr(incidents, "get_settings", lambda: settings)

    seen: dict[str, object] = {}

    async def _fake_resolve(tenant_id: str | None):
        seen["tenant_id"] = tenant_id
        return "resolved-token", "resolved-org"

    monkeypatch.setattr(incidents, "resolve_github_creds", _fake_resolve)

    class _FakeContext:
        def model_dump(self, mode: str = "json"):
            assert mode == "json"
            return {"repo": "resolved-org/payments-api"}

    class _FakeGitHubAdapter:
        @classmethod
        def from_credentials(cls, token: str, org: str, provided_settings):
            seen["from_credentials"] = (token, org, provided_settings)
            return cls()

        def _get_repo_for_service(self, service_name: str):
            return f"resolved-org/{service_name}"

        async def get_context(self, service: str):
            seen["service"] = service
            return _FakeContext()

    monkeypatch.setattr(incidents, "GitHubAdapter", _FakeGitHubAdapter)

    payload = await incidents._try_ondemand_enrichment(
        {"id": "inc-1", "service": "payments-api"},
        tenant_id="tenant-1",
    )

    assert isinstance(GitHubAdapter, type)  # keep import path exercised
    assert seen["tenant_id"] == "tenant-1"
    assert seen["service"] == "payments-api"
    token, org, provided_settings = seen["from_credentials"]
    assert token == "resolved-token"
    assert org == "resolved-org"
    assert provided_settings is settings
    assert payload == {
        "github": {"repo": "resolved-org/payments-api"},
        "github_context": {"repo": "resolved-org/payments-api"},
    }


@pytest.mark.asyncio
async def test_try_ondemand_enrichment_logs_no_token(monkeypatch):
    from src.api import incidents

    logs: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        incidents, "resolve_github_creds", AsyncMock(return_value=("", ""))
    )
    monkeypatch.setattr(
        incidents,
        "logger",
        SimpleNamespace(
            warning=lambda event, **kwargs: logs.append((event, kwargs)),
        ),
    )

    payload = await incidents._try_ondemand_enrichment(
        {"id": "inc-1", "service": "payments-api"},
        tenant_id="tenant-1",
    )

    assert payload == {}
    assert logs == [
        (
            "ondemand_github_enrichment_skipped",
            {
                "reason": "no_token",
                "tenant_id": "tenant-1",
                "service": "payments-api",
            },
        )
    ]


@pytest.mark.asyncio
async def test_try_ondemand_enrichment_logs_no_org_when_repo_cannot_be_resolved(
    monkeypatch,
):
    from src.api import incidents

    logs: list[tuple[str, dict[str, object]]] = []
    settings = SimpleNamespace(service_repo_map={})

    monkeypatch.setattr(incidents, "get_settings", lambda: settings)
    monkeypatch.setattr(
        incidents, "resolve_github_creds", AsyncMock(return_value=("token", ""))
    )
    monkeypatch.setattr(
        incidents,
        "logger",
        SimpleNamespace(
            warning=lambda event, **kwargs: logs.append((event, kwargs)),
        ),
    )

    payload = await incidents._try_ondemand_enrichment(
        {"id": "inc-2", "service": "payments-api"},
        tenant_id="tenant-2",
    )

    assert payload == {}
    assert logs == [
        (
            "ondemand_github_enrichment_skipped",
            {
                "reason": "no_org",
                "tenant_id": "tenant-2",
                "service": "payments-api",
                "has_org": False,
                "has_service_mapping": False,
            },
        )
    ]


@pytest.mark.asyncio
async def test_try_ondemand_enrichment_logs_api_error_reason(monkeypatch):
    from src.api import incidents

    logs: list[tuple[str, dict[str, object]]] = []
    settings = SimpleNamespace(service_repo_map={})

    class _FakeGitHubAdapter:
        last_context_error_reason = "api_error"

        @classmethod
        def from_credentials(cls, token: str, org: str, provided_settings):
            assert token == "token"
            assert org == "my-org"
            assert provided_settings is settings
            return cls()

        def _get_repo_for_service(self, service_name: str):
            assert service_name == "payments-api"
            return "my-org/payments-api"

        async def get_context(self, service_name: str):
            assert service_name == "payments-api"
            return None

    monkeypatch.setattr(incidents, "get_settings", lambda: settings)
    monkeypatch.setattr(
        incidents, "resolve_github_creds", AsyncMock(return_value=("token", "my-org"))
    )
    monkeypatch.setattr(incidents, "GitHubAdapter", _FakeGitHubAdapter)
    monkeypatch.setattr(
        incidents,
        "logger",
        SimpleNamespace(
            warning=lambda event, **kwargs: logs.append((event, kwargs)),
        ),
    )

    payload = await incidents._try_ondemand_enrichment(
        {"id": "inc-3", "service": "payments-api"},
        tenant_id="tenant-3",
    )

    assert payload == {}
    assert logs == [
        (
            "ondemand_github_enrichment_skipped",
            {
                "reason": "api_error",
                "tenant_id": "tenant-3",
                "incident_id": "inc-3",
                "service": "payments-api",
            },
        )
    ]


@pytest.mark.asyncio
async def test_github_adapter_logs_debug_when_repo_is_unresolved(monkeypatch):
    logs: list[tuple[str, dict[str, object]]] = []
    settings = SimpleNamespace(github_token="token", github_org="", service_repo_map={})

    monkeypatch.setattr(
        "src.integrations.github.logger",
        SimpleNamespace(
            debug=lambda event, **kwargs: logs.append((event, kwargs)),
            error=lambda *args, **kwargs: None,
        ),
    )

    adapter = GitHubAdapter(settings)

    context = await adapter.get_context("payments-api")

    assert context is None
    assert adapter.last_context_error_reason == "no_repo_mapping"
    assert logs == [
        (
            "github_context_repo_unresolved",
            {
                "service": "payments-api",
                "has_org": False,
                "has_service_mapping": False,
            },
        )
    ]
