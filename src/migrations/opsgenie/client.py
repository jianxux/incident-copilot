"""Opsgenie REST API v2 client with rate limiting and pagination."""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.opsgenie.com/v2"


class OpsgenieClient:
    """Async client for the Opsgenie v2 API."""

    def __init__(self, api_key: str, base_url: str = BASE_URL) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._semaphore = asyncio.Semaphore(5)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"GenieKey {self.api_key}"},
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a rate-limited request to the Opsgenie API."""
        async with self._semaphore:
            client = await self._get_client()
            resp = await client.request(method, path, params=params)
            resp.raise_for_status()
            return resp.json()

    async def _paginate(
        self,
        path: str,
        data_key: str = "data",
        limit: int = 0,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Paginate through a list endpoint."""
        results: list[dict[str, Any]] = []
        offset = 0
        while True:
            params = {"limit": page_size, "offset": offset}
            body = await self._request("GET", path, params=params)
            page = body.get(data_key, [])
            results.extend(page)
            if limit and len(results) >= limit:
                return results[:limit]
            paging = body.get("paging", {})
            if not paging.get("next"):
                break
            offset += page_size
        return results

    async def validate_api_key(self) -> bool:
        """Check if the API key is valid by hitting /account."""
        try:
            await self._request("GET", "/account")
            return True
        except httpx.HTTPStatusError:
            return False

    async def get_services(self) -> list[dict[str, Any]]:
        return await self._paginate("/services")

    async def get_teams(self) -> list[dict[str, Any]]:
        return await self._paginate("/teams")

    async def get_users(self) -> list[dict[str, Any]]:
        return await self._paginate("/users")

    async def get_schedules(self) -> list[dict[str, Any]]:
        return await self._paginate("/schedules")

    async def get_escalations(self) -> list[dict[str, Any]]:
        return await self._paginate("/escalations")

    async def get_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        return await self._paginate("/alerts", limit=limit)

    async def get_integrations(self) -> list[dict[str, Any]]:
        body = await self._request("GET", "/integrations")
        return body.get("data", [])
