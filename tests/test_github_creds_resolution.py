from __future__ import annotations

from types import SimpleNamespace

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
    monkeypatch.setattr(
        "src.integrations.github.get_db",
        lambda use_admin=True: _FakeDB([{"config": {"encrypted": "encrypted-payload"}}]),
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

    class _FailingDB:
        client = SimpleNamespace(table=lambda _name: None)

        async def _to_thread(self, fn, *args, **kwargs):
            raise RuntimeError("db unavailable")

    monkeypatch.setattr("src.integrations.github.get_db", lambda use_admin=True: _FailingDB())

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
