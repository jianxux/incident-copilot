"""Data models for the plugin framework."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PluginType(StrEnum):
    WEBHOOK = "webhook"
    ENRICHMENT = "enrichment"
    FILTER = "filter"


class PluginStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class PluginEvent(StrEnum):
    INCIDENT_TRIGGERED = "incident.triggered"
    INCIDENT_RESOLVED = "incident.resolved"
    INCIDENT_UPDATED = "incident.updated"
    CONTEXT_ASSEMBLED = "context.assembled"
    POSTMORTEM_CREATED = "postmortem.created"


class RetryConfig(BaseModel):
    max_retries: int = Field(default=3, ge=0, le=10)
    initial_delay_ms: int = Field(default=1000, ge=100, le=30000)
    max_delay_ms: int = Field(default=30000, ge=1000, le=300000)
    backoff_multiplier: float = Field(default=2.0, ge=1.0, le=5.0)


class HmacConfig(BaseModel):
    secret: str
    algorithm: str = "sha256"
    header_name: str = "X-Webhook-Signature"

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        if v.lower() not in {"sha256", "sha512", "sha1"}:
            raise ValueError("Algorithm must be sha256, sha512, or sha1")
        return v.lower()


class WebhookConfig(BaseModel):
    url: str
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_ms: int = Field(default=10000, ge=1000, le=60000)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    hmac: HmacConfig | None = None
    payload_template: str | None = None
    include_full_card: bool = True


class EnrichmentConfig(BaseModel):
    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_ms: int = Field(default=5000, ge=500, le=30000)
    query_params_template: dict[str, str] = Field(default_factory=dict)
    body_template: str | None = None
    response_field: str | None = None
    target_field: str = "custom_enrichment"
    cache_ttl_seconds: int = Field(default=300, ge=0, le=86400)


class FilterCondition(BaseModel):
    field: str
    operator: str
    value: Any

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        if v.lower() not in {
            "eq",
            "ne",
            "in",
            "not_in",
            "contains",
            "matches",
            "gt",
            "lt",
            "gte",
            "lte",
        }:
            raise ValueError(
                "Operator must be eq, ne, in, not_in, contains, matches, gt, lt, gte, or lte"
            )
        return v.lower()


class FilterConfig(BaseModel):
    conditions: list[FilterCondition] = Field(default_factory=list)
    match_mode: str = "all"
    action: str = "include"
    modifications: dict[str, Any] = Field(default_factory=dict)


class PluginMetrics(BaseModel):
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    avg_latency_ms: float = 0.0
    last_execution_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0


class Plugin(BaseModel):
    id: str
    name: str
    description: str = ""
    type: PluginType
    status: PluginStatus = PluginStatus.ACTIVE
    events: list[PluginEvent] = Field(default_factory=list)
    priority: int = Field(default=100, ge=1, le=1000)
    webhook_config: WebhookConfig | None = None
    enrichment_config: EnrichmentConfig | None = None
    filter_config: FilterConfig | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metrics: PluginMetrics = Field(default_factory=PluginMetrics)
    max_consecutive_failures: int = 5


class PluginCreateRequest(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-_]*[a-z0-9]$", min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    type: PluginType
    events: list[PluginEvent] = Field(default_factory=lambda: [PluginEvent.CONTEXT_ASSEMBLED])
    priority: int = Field(default=100, ge=1, le=1000)
    webhook_config: WebhookConfig | None = None
    enrichment_config: EnrichmentConfig | None = None
    filter_config: FilterConfig | None = None


class PluginUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: PluginStatus | None = None
    events: list[PluginEvent] | None = None
    priority: int | None = None
    webhook_config: WebhookConfig | None = None
    enrichment_config: EnrichmentConfig | None = None
    filter_config: FilterConfig | None = None


class PluginTestRequest(BaseModel):
    sample_data: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True


class PluginTestResult(BaseModel):
    success: bool
    plugin_id: str
    plugin_type: PluginType
    execution_time_ms: int
    request_payload: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class WebhookDelivery(BaseModel):
    id: str
    plugin_id: str
    event: PluginEvent
    url: str
    method: str
    request_headers: dict[str, str]
    request_body: str
    response_status: int | None = None
    response_body: str | None = None
    attempt_number: int = 1
    success: bool = False
    error: str | None = None
    latency_ms: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
