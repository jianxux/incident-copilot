"""Webhook executor with retry logic and HMAC signatures."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import aiohttp
import structlog

from .models import HmacConfig, PluginEvent, RetryConfig, WebhookDelivery

logger = structlog.get_logger()


class WebhookExecutor:
    def __init__(self):
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def send(
        self,
        url: str,
        method: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout_ms: int = 10000,
        retry_config: RetryConfig | None = None,
        hmac_config: HmacConfig | None = None,
        plugin_id: str = "",
        event: PluginEvent | None = None,
    ) -> WebhookDelivery:
        retry_config = retry_config or RetryConfig()
        headers = dict(headers or {})
        body = json.dumps(payload, default=str)
        body_bytes = body.encode("utf-8")
        headers.update({
            "Content-Type": "application/json",
            "X-Webhook-Event": event.value if event else "unknown",
            "X-Webhook-Plugin": plugin_id,
            "X-Webhook-Delivery": str(uuid.uuid4()),
            "X-Webhook-Timestamp": str(int(time.time())),
        })
        if hmac_config:
            headers[hmac_config.header_name] = self._compute_signature(
                body_bytes, hmac_config.secret, hmac_config.algorithm
            )
        delivery = WebhookDelivery(
            id=headers["X-Webhook-Delivery"],
            plugin_id=plugin_id,
            event=event or PluginEvent.CONTEXT_ASSEMBLED,
            url=url,
            method=method,
            request_headers={k: v for k, v in headers.items() if not k.lower().startswith("x-")},
            request_body=body[:10000],
        )
        attempt, last_error, total_start = 0, None, time.monotonic()
        while attempt <= retry_config.max_retries:
            attempt += 1
            delivery.attempt_number = attempt
            try:
                result = await self._attempt_delivery(url, method, body_bytes, headers, timeout_ms)
                delivery.response_status, delivery.response_body = (
                    result["status"],
                    (result["body"][:10000] if result["body"] else None),
                )
                delivery.success = 200 <= result["status"] < 300
                delivery.latency_ms = int((time.monotonic() - total_start) * 1000)
                if delivery.success:
                    return delivery
                if result["status"] in {400, 401, 403, 404, 405, 422}:
                    delivery.error = f"HTTP {result['status']}: Non-retryable"
                    return delivery
                last_error = f"HTTP {result['status']}"
            except (TimeoutError, aiohttp.ClientError, Exception) as e:
                last_error = str(e)
            if attempt <= retry_config.max_retries:
                await asyncio.sleep(
                    self._calculate_delay(
                        attempt,
                        retry_config.initial_delay_ms,
                        retry_config.max_delay_ms,
                        retry_config.backoff_multiplier,
                    )
                    / 1000
                )
        delivery.error, delivery.latency_ms = (
            last_error,
            int((time.monotonic() - total_start) * 1000),
        )
        return delivery

    async def _attempt_delivery(
        self,
        url: str,
        method: str,
        body: bytes,
        headers: dict[str, str],
        timeout_ms: int,
    ) -> dict[str, Any]:
        session = await self._get_session()
        async with session.request(
            method=method,
            url=url,
            data=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout_ms / 1000),
        ) as resp:
            return {"status": resp.status, "body": await resp.text()}

    def _compute_signature(self, body: bytes, secret: str, algorithm: str) -> str:
        h = {
            "sha256": hashlib.sha256,
            "sha512": hashlib.sha512,
            "sha1": hashlib.sha1,
        }.get(algorithm, hashlib.sha256)
        return f"{algorithm}={hmac.new(secret.encode(), body, h).hexdigest()}"

    def _calculate_delay(
        self, attempt: int, initial_delay_ms: int, max_delay_ms: int, multiplier: float
    ) -> int:
        import random

        return min(
            int(initial_delay_ms * (multiplier ** (attempt - 1)) * random.uniform(0.75, 1.25)),
            max_delay_ms,
        )

    @staticmethod
    def verify_signature(body: bytes, signature: str, secret: str) -> bool:
        try:
            algo, expected = signature.split("=", 1)
            h = {
                "sha256": hashlib.sha256,
                "sha512": hashlib.sha512,
                "sha1": hashlib.sha1,
            }.get(algo)
            return h and hmac.compare_digest(
                hmac.new(secret.encode(), body, h).hexdigest(), expected
            )
        except Exception:
            return False
