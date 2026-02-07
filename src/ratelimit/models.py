"""Data models for rate limiting."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RateLimitScope(StrEnum):
    """Scope for rate limiting."""

    IP = "ip"  # Per IP address
    API_KEY = "api_key"  # Per API key
    TENANT = "tenant"  # Per tenant/organization
    USER = "user"  # Per user
    ENDPOINT = "endpoint"  # Per endpoint (combined with other scopes)
    GLOBAL = "global"  # Global limit


class RateLimitConfig(BaseModel):
    """Configuration for a rate limit rule."""

    # Identifiers
    name: str = Field(..., description="Human-readable name for this limit")
    scope: RateLimitScope = Field(..., description="Scope of the rate limit")

    # Token bucket parameters
    capacity: int = Field(
        default=100, ge=1, description="Maximum tokens in the bucket (burst capacity)"
    )
    refill_rate: float = Field(
        default=10.0, gt=0, description="Tokens added per second"
    )
    refill_interval: float = Field(
        default=1.0, gt=0, description="Interval in seconds between refills"
    )

    # Optional constraints
    endpoints: list[str] | None = Field(
        default=None,
        description="Specific endpoints this limit applies to (regex patterns)",
    )
    methods: list[str] | None = Field(
        default=None, description="HTTP methods this limit applies to"
    )

    # Behavior
    enabled: bool = Field(default=True, description="Whether this limit is active")
    cost: int = Field(default=1, description="Default token cost per request")

    # Metadata
    description: str | None = None

    @property
    def tokens_per_minute(self) -> float:
        """Calculate approximate tokens per minute for display."""
        return self.refill_rate * 60

    @property
    def tokens_per_hour(self) -> float:
        """Calculate approximate tokens per hour for display."""
        return self.refill_rate * 3600


class RateLimitResult(BaseModel):
    """Result of a rate limit check."""

    allowed: bool = Field(..., description="Whether the request is allowed")
    limit: int = Field(..., description="Maximum tokens (bucket capacity)")
    remaining: int = Field(..., description="Remaining tokens")
    reset_at: datetime = Field(
        ..., description="When the bucket will be fully refilled"
    )
    retry_after: float | None = Field(
        default=None, description="Seconds to wait before retrying (if denied)"
    )

    # Context
    scope: RateLimitScope = Field(..., description="Scope that triggered this result")
    key: str = Field(..., description="The rate limit key that was checked")
    cost: int = Field(default=1, description="Token cost for this request")

    def to_headers(self) -> dict[str, str]:
        """Convert to HTTP headers for the response."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_at.timestamp())),
        }
        if self.retry_after is not None:
            headers["Retry-After"] = str(int(self.retry_after))
        return headers


class RateLimitStatus(BaseModel):
    """Status of rate limits for an entity."""

    key: str = Field(..., description="The rate limit key")
    scope: RateLimitScope = Field(..., description="Scope of the limit")
    current_tokens: float = Field(..., description="Current tokens in bucket")
    capacity: int = Field(..., description="Maximum bucket capacity")
    refill_rate: float = Field(..., description="Tokens added per second")
    last_refill: datetime = Field(..., description="Last time tokens were refilled")
    requests_in_window: int = Field(
        default=0, description="Total requests in current window"
    )

    # Computed
    @property
    def utilization(self) -> float:
        """Utilization as percentage (0-100)."""
        if self.capacity == 0:
            return 100.0
        return ((self.capacity - self.current_tokens) / self.capacity) * 100


class RateLimitOverride(BaseModel):
    """Override rate limit for a specific key."""

    key: str = Field(..., description="The key to override (e.g., tenant ID, API key)")
    scope: RateLimitScope = Field(..., description="Scope of the override")
    capacity: int | None = Field(default=None, description="Override capacity")
    refill_rate: float | None = Field(default=None, description="Override refill rate")
    enabled: bool = Field(default=True, description="Whether override is active")
    expires_at: datetime | None = Field(
        default=None, description="When this override expires"
    )
    reason: str | None = Field(default=None, description="Reason for the override")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = Field(
        default=None, description="User who created override"
    )


class EndpointRateLimit(BaseModel):
    """Rate limit configuration for a specific endpoint."""

    path_pattern: str = Field(..., description="Regex pattern for endpoint path")
    methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE"],
        description="HTTP methods this applies to",
    )
    capacity: int = Field(default=100, description="Bucket capacity")
    refill_rate: float = Field(default=10.0, description="Tokens per second")
    cost: int = Field(default=1, description="Token cost per request")

    # Can override per-scope limits
    override_global: bool = Field(
        default=False, description="Whether this overrides global limits"
    )


class RateLimitEvent(BaseModel):
    """Event emitted when rate limit is exceeded."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    key: str
    scope: RateLimitScope
    ip_address: str | None = None
    tenant_id: str | None = None
    api_key_id: str | None = None
    user_id: str | None = None
    endpoint: str
    method: str
    current_tokens: float
    limit: int
    metadata: dict[str, Any] = Field(default_factory=dict)
