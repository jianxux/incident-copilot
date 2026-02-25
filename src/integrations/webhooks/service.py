"""Webhook delivery service with retry logic and circuit breaker."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, UTC
from typing import Any
from uuid import UUID

import httpx

from .models import (
    CircuitState,
    DeliveryStatus,
    WebhookConfig,
    WebhookDelivery,
    WebhookEvent,
    WebhookEventType,
    WebhookStats,
)
from .signatures import generate_signature
from .templates import render_webhook_payload

logger = logging.getLogger(__name__)


# Circuit breaker settings
FAILURE_THRESHOLD = 5
RECOVERY_TIMEOUT_SECONDS = 60
HALF_OPEN_MAX_CALLS = 3

# Retry settings
RETRY_BASE_DELAY_SECONDS = 5
RETRY_MAX_DELAY_SECONDS = 3600  # 1 hour
RETRY_BACKOFF_MULTIPLIER = 2


class CircuitBreaker:
    """Circuit breaker for webhook endpoints."""

    def __init__(self, config: WebhookConfig):
        self.config = config

    def can_execute(self) -> bool:
        """Check if request can be made."""
        if self.config.circuit_state == CircuitState.CLOSED:
            return True

        if self.config.circuit_state == CircuitState.OPEN:
            # Check if recovery timeout passed
            if self.config.circuit_opened_at:
                recovery_time = self.config.circuit_opened_at + timedelta(
                    seconds=RECOVERY_TIMEOUT_SECONDS
                )
                if datetime.now(UTC) >= recovery_time:
                    self.config.circuit_state = CircuitState.HALF_OPEN
                    self.config.failure_count = 0
                    return True
            return False

        # HALF_OPEN - allow limited requests
        return self.config.failure_count < HALF_OPEN_MAX_CALLS

    def record_success(self) -> None:
        """Record successful request."""
        if self.config.circuit_state == CircuitState.HALF_OPEN:
            self.config.circuit_state = CircuitState.CLOSED
        self.config.failure_count = 0
        self.config.last_failure_at = None

    def record_failure(self) -> None:
        """Record failed request."""
        self.config.failure_count += 1
        self.config.last_failure_at = datetime.now(UTC)

        if self.config.failure_count >= FAILURE_THRESHOLD:
            self.config.circuit_state = CircuitState.OPEN
            self.config.circuit_opened_at = datetime.now(UTC)
            logger.warning(f"Circuit opened for webhook {self.config.id}")


class WebhookDeliveryService:
    """Service for delivering webhooks with retries."""

    def __init__(self):
        self._webhooks: dict[UUID, WebhookConfig] = {}
        self._deliveries: dict[UUID, WebhookDelivery] = {}
        self._pending_retries: asyncio.Queue[WebhookDelivery] = asyncio.Queue()
        self._circuit_breakers: dict[UUID, CircuitBreaker] = {}
        self._retry_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the retry background task."""
        self._retry_task = asyncio.create_task(self._retry_loop())
        logger.info("Webhook delivery service started")

    async def stop(self) -> None:
        """Stop the retry background task."""
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
        logger.info("Webhook delivery service stopped")

    def register_webhook(self, config: WebhookConfig) -> None:
        """Register a webhook configuration."""
        self._webhooks[config.id] = config
        self._circuit_breakers[config.id] = CircuitBreaker(config)

    def unregister_webhook(self, webhook_id: UUID) -> None:
        """Unregister a webhook."""
        self._webhooks.pop(webhook_id, None)
        self._circuit_breakers.pop(webhook_id, None)

    def get_webhook(self, webhook_id: UUID) -> WebhookConfig | None:
        """Get webhook by ID."""
        return self._webhooks.get(webhook_id)

    def get_webhooks_for_org(self, organization_id: UUID) -> list[WebhookConfig]:
        """Get all webhooks for an organization."""
        return [
            w for w in self._webhooks.values() if w.organization_id == organization_id
        ]

    def get_active_webhooks_for_event(
        self, organization_id: UUID, event_type: WebhookEventType
    ) -> list[WebhookConfig]:
        """Get active webhooks subscribed to event type."""
        return [
            w
            for w in self._webhooks.values()
            if w.organization_id == organization_id
            and w.is_active
            and event_type in w.events
        ]

    async def deliver(
        self, event: WebhookEvent, webhook_ids: list[UUID] | None = None
    ) -> list[WebhookDelivery]:
        """Deliver event to webhooks."""
        if webhook_ids:
            webhooks = [
                self._webhooks[wid] for wid in webhook_ids if wid in self._webhooks
            ]
        else:
            webhooks = self.get_active_webhooks_for_event(
                event.organization_id, event.event_type
            )

        deliveries = []
        for webhook in webhooks:
            delivery = await self._deliver_to_webhook(event, webhook)
            deliveries.append(delivery)

        return deliveries

    async def deliver_bulk(
        self,
        events: list[WebhookEvent],
        webhook_ids: list[UUID] | None = None,
        concurrency: int = 10,
    ) -> list[WebhookDelivery]:
        """Deliver multiple events with concurrency control."""
        semaphore = asyncio.Semaphore(concurrency)

        async def deliver_with_limit(event: WebhookEvent) -> list[WebhookDelivery]:
            async with semaphore:
                return await self.deliver(event, webhook_ids)

        results = await asyncio.gather(
            *[deliver_with_limit(e) for e in events], return_exceptions=True
        )

        deliveries = []
        for result in results:
            if isinstance(result, list):
                deliveries.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Bulk delivery error: {result}")

        return deliveries

    async def _deliver_to_webhook(
        self, event: WebhookEvent, webhook: WebhookConfig, attempt: int = 1
    ) -> WebhookDelivery:
        """Deliver event to a specific webhook."""
        circuit = self._circuit_breakers.get(webhook.id)

        # Check circuit breaker
        if circuit and not circuit.can_execute():
            delivery = WebhookDelivery(
                webhook_id=webhook.id,
                event_id=event.id,
                event_type=event.event_type,
                url=str(webhook.url),
                status=DeliveryStatus.FAILED,
                attempt_number=attempt,
                error_message="Circuit breaker open",
            )
            self._deliveries[delivery.id] = delivery
            return delivery

        # Render payload
        payload = render_webhook_payload(event, webhook.payload_template_id)
        payload_json = json.dumps(payload, default=str)

        # Generate signature
        signature, timestamp = generate_signature(payload_json, webhook.secret)

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": str(timestamp),
            "X-Webhook-Event": event.event_type.value,
            "X-Webhook-Delivery-Id": str(event.id),
            "User-Agent": "IncidentCopilot-Webhook/1.0",
            **webhook.custom_headers,
        }

        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            event_id=event.id,
            event_type=event.event_type,
            url=str(webhook.url),
            attempt_number=attempt,
            request_headers=headers,
            request_body=payload_json,
        )

        start_time = datetime.now(UTC)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    str(webhook.url),
                    content=payload_json,
                    headers=headers,
                    timeout=webhook.timeout_seconds,
                )

            duration = (datetime.now(UTC) - start_time).total_seconds() * 1000

            delivery.response_status_code = response.status_code
            delivery.response_body = response.text[:10000]  # Limit size
            delivery.response_headers = dict(response.headers)
            delivery.duration_ms = int(duration)
            delivery.delivered_at = datetime.now(UTC)

            if 200 <= response.status_code < 300:
                delivery.status = DeliveryStatus.DELIVERED
                if circuit:
                    circuit.record_success()
                webhook.successful_deliveries += 1
            else:
                delivery.status = DeliveryStatus.FAILED
                delivery.error_message = f"HTTP {response.status_code}"
                if circuit:
                    circuit.record_failure()
                webhook.failed_deliveries += 1

                # Schedule retry if allowed
                if attempt < webhook.max_retries:
                    await self._schedule_retry(delivery, webhook)

        except httpx.TimeoutException:
            delivery.status = DeliveryStatus.FAILED
            delivery.error_message = "Request timeout"
            delivery.duration_ms = webhook.timeout_seconds * 1000
            if circuit:
                circuit.record_failure()
            webhook.failed_deliveries += 1
            if attempt < webhook.max_retries:
                await self._schedule_retry(delivery, webhook)

        except httpx.RequestError as e:
            delivery.status = DeliveryStatus.FAILED
            delivery.error_message = str(e)
            if circuit:
                circuit.record_failure()
            webhook.failed_deliveries += 1
            if attempt < webhook.max_retries:
                await self._schedule_retry(delivery, webhook)

        webhook.total_deliveries += 1
        self._deliveries[delivery.id] = delivery

        logger.info(
            f"Webhook delivery {delivery.id}: {delivery.status.value} "
            f"(attempt {attempt}, {delivery.duration_ms}ms)"
        )

        return delivery

    async def _schedule_retry(
        self, delivery: WebhookDelivery, webhook: WebhookConfig
    ) -> None:
        """Schedule a delivery for retry."""
        delay = min(
            RETRY_BASE_DELAY_SECONDS
            * (RETRY_BACKOFF_MULTIPLIER**delivery.attempt_number),
            RETRY_MAX_DELAY_SECONDS,
        )
        delivery.status = DeliveryStatus.RETRYING
        delivery.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
        await self._pending_retries.put(delivery)
        logger.info(f"Scheduled retry for {delivery.id} in {delay}s")

    async def _retry_loop(self) -> None:
        """Background loop for processing retries."""
        while True:
            try:
                delivery = await self._pending_retries.get()

                if delivery.next_retry_at:
                    wait_seconds = (
                        delivery.next_retry_at - datetime.now(UTC)
                    ).total_seconds()
                    if wait_seconds > 0:
                        await asyncio.sleep(wait_seconds)

                webhook = self._webhooks.get(delivery.webhook_id)
                if not webhook:
                    continue

                # Reconstruct event for retry
                event = WebhookEvent(
                    id=delivery.event_id,
                    event_type=delivery.event_type,
                    organization_id=webhook.organization_id,
                    payload=json.loads(delivery.request_body).get("data", {}),
                )

                await self._deliver_to_webhook(
                    event, webhook, delivery.attempt_number + 1
                )

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Retry loop error: {e}")

    async def test_webhook(
        self,
        webhook: WebhookConfig,
        event_type: WebhookEventType = WebhookEventType.INCIDENT_CREATED,
        custom_payload: dict[str, Any] | None = None,
    ) -> WebhookDelivery:
        """Test a webhook with a sample event."""
        test_event = WebhookEvent(
            event_type=event_type,
            organization_id=webhook.organization_id,
            payload=custom_payload
            or {
                "incident_id": "test-incident-123",
                "title": "Test Incident",
                "description": "This is a test webhook delivery",
                "severity": "low",
                "status": "open",
                "created_at": datetime.now(UTC).isoformat(),
                "incident_url": "https://example.com/incidents/test-123",
            },
            correlation_id="test-delivery",
        )

        # Temporarily disable retries for test
        original_retries = webhook.max_retries
        webhook.max_retries = 0

        try:
            delivery = await self._deliver_to_webhook(test_event, webhook)
        finally:
            webhook.max_retries = original_retries

        return delivery

    def get_delivery(self, delivery_id: UUID) -> WebhookDelivery | None:
        """Get delivery by ID."""
        return self._deliveries.get(delivery_id)

    def get_deliveries_for_webhook(
        self, webhook_id: UUID, limit: int = 100
    ) -> list[WebhookDelivery]:
        """Get recent deliveries for a webhook."""
        deliveries = [
            d for d in self._deliveries.values() if d.webhook_id == webhook_id
        ]
        deliveries.sort(key=lambda d: d.created_at, reverse=True)
        return deliveries[:limit]

    def get_stats(self, webhook_id: UUID) -> WebhookStats | None:
        """Get statistics for a webhook."""
        webhook = self._webhooks.get(webhook_id)
        if not webhook:
            return None

        deliveries = self.get_deliveries_for_webhook(webhook_id)

        durations = [d.duration_ms for d in deliveries if d.duration_ms]
        avg_duration = sum(durations) / len(durations) if durations else None

        last_delivery = deliveries[0].created_at if deliveries else None

        success_rate = (
            webhook.successful_deliveries / webhook.total_deliveries * 100
            if webhook.total_deliveries > 0
            else 0.0
        )

        return WebhookStats(
            webhook_id=webhook_id,
            total_deliveries=webhook.total_deliveries,
            successful_deliveries=webhook.successful_deliveries,
            failed_deliveries=webhook.failed_deliveries,
            success_rate=success_rate,
            avg_response_time_ms=avg_duration,
            last_delivery_at=last_delivery,
            circuit_state=webhook.circuit_state,
        )


# Global service instance
webhook_service = WebhookDeliveryService()
