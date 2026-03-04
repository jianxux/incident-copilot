from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Settings
from src.services.discovery import ServiceCatalogDiscovery


@pytest.mark.asyncio
@pytest.mark.parametrize("verify_ssl", [True, False])
async def test_discover_from_kubernetes_uses_configured_verify_ssl(
    monkeypatch: pytest.MonkeyPatch, verify_ssl: bool
):
    settings = Settings(kubernetes_verify_ssl=verify_ssl)
    store = MagicMock()
    store.create_service = AsyncMock()
    discovery = ServiceCatalogDiscovery(settings, store)

    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")

    def fake_exists(path: str) -> bool:
        return path in {
            "/var/run/secrets/kubernetes.io/serviceaccount/token",
            "/var/run/secrets/kubernetes.io/serviceaccount/namespace",
        }

    def fake_open(path: str, encoding: str = "utf-8"):  # noqa: ARG001
        if path.endswith("/token"):
            return io.StringIO("test-token")
        if path.endswith("/namespace"):
            return io.StringIO("test-namespace")
        raise FileNotFoundError(path)

    monkeypatch.setattr("src.services.discovery.os.path.exists", fake_exists)
    monkeypatch.setattr("builtins.open", fake_open)

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "items": [
            {
                "metadata": {"name": "payments", "namespace": "prod"},
                "spec": {"type": "ClusterIP", "clusterIP": "10.0.0.1"},
            }
        ]
    }

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client_cm = AsyncMock()
    client_cm.__aenter__.return_value = client

    async_client_ctor = MagicMock(return_value=client_cm)
    monkeypatch.setattr("src.services.discovery.httpx.AsyncClient", async_client_ctor)

    result = await discovery.discover_from_kubernetes(tenant_slug="tenant-a")

    async_client_ctor.assert_called_once_with(timeout=20.0, verify=verify_ssl)
    client.get.assert_awaited_once()
    store.create_service.assert_awaited_once()
    assert result == {"discovered": 1, "created": 1, "skipped": 0}


def test_settings_kubernetes_verify_ssl_defaults_true():
    assert Settings().kubernetes_verify_ssl is True


def test_settings_kubernetes_verify_ssl_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KUBERNETES_VERIFY_SSL", "false")
    assert Settings().kubernetes_verify_ssl is False
