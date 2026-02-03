"""Rate limiter implementation using token bucket algorithm with Redis backend."""

import asyncio
import hashlib
import re
import time
from datetime import datetime, timedelta

import structlog
from redis import asyncio as aioredis

from src.config import get_settings

from .models import (
    EndpointRateLimit,
    RateLimitConfig,
    RateLimitEvent,
    RateLimitOverride,
    RateLimitResult,
    RateLimitScope,
    RateLimitStatus,
)

logger = structlog.get_logger()


class RateLimiter:
    """Token bucket rate limiter with Redis backend.

    Implements the token bucket algorithm:
    - Each bucket has a capacity (max tokens)
    - Tokens are added at a fixed rate
    - Each request consumes tokens
    - If not enough tokens, request is denied

    Benefits of token bucket:
    - Allows bursts up to capacity
    - Smooth rate limiting over time
    - Redis atomic operations prevent race conditions
    """

    # Lua script for atomic token bucket operation
    TOKEN_BUCKET_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local cost = tonumber(ARGV[4])
    local ttl = tonumber(ARGV[5])
    
    -- Get current bucket state
    local bucket = redis.call('HMGET', key, 'tokens', 'last_update')
    local tokens = tonumber(bucket[1])
    local last_update = tonumber(bucket[2])
    
    -- Initialize bucket if it doesn't exist
    if tokens == nil then
        tokens = capacity
        last_update = now
    end
    
    -- Calculate tokens to add based on time elapsed
    local elapsed = now - last_update
    local tokens_to_add = elapsed * refill_rate
    tokens = math.min(capacity, tokens + tokens_to_add)
    
    -- Check if request can be allowed
    local allowed = 0
    local remaining = tokens
    local retry_after = 0
    
    if tokens >= cost then
        -- Consume tokens
        tokens = tokens - cost
        remaining = tokens
        allowed = 1
    else
        -- Calculate retry time
        retry_after = (cost - tokens) / refill_rate
        remaining = tokens
    end
    
    -- Update bucket state
    redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
    redis.call('EXPIRE', key, ttl)
    
    -- Increment request counter for stats
    local counter_key = key .. ':requests'
    redis.call('INCR', counter_key)
    redis.call('EXPIRE', counter_key, 3600)  -- 1 hour window for stats
    
    return {allowed, remaining, retry_after}
    """

    def __init__(
        self,
        redis_url: str | None = None,
        key_prefix: str = "ratelimit",
        default_configs: list[RateLimitConfig] | None = None,
    ):
        settings = get_settings()
        self.redis_url = redis_url or settings.redis_url
        self.key_prefix = key_prefix
        self._redis: aioredis.Redis | None = None
        self._script_sha: str | None = None

        # Default configurations per scope
        self._configs: dict[RateLimitScope, RateLimitConfig] = {}
        self._endpoint_limits: list[EndpointRateLimit] = []
        self._overrides: dict[str, RateLimitOverride] = {}

        # In-memory fallback when Redis unavailable
        self._memory_buckets: dict[str, dict[str, float]] = {}
        self._use_memory_fallback = False

        # Initialize default configs
        self._init_default_configs(default_configs)

        # Event callbacks
        self._on_limit_exceeded: list[callable] = []

    def _init_default_configs(self, configs: list[RateLimitConfig] | None) -> None:
        """Initialize default rate limit configurations."""
        settings = get_settings()

        if configs:
            for config in configs:
                self._configs[config.scope] = config
        else:
            # Load from settings or use defaults
            self._configs = {
                RateLimitScope.IP: RateLimitConfig(
                    name="IP Rate Limit",
                    scope=RateLimitScope.IP,
                    capacity=settings.ratelimit_ip_capacity,
                    refill_rate=settings.ratelimit_ip_refill_rate,
                    description="Per-IP address rate limit",
                ),
                RateLimitScope.API_KEY: RateLimitConfig(
                    name="API Key Rate Limit",
                    scope=RateLimitScope.API_KEY,
                    capacity=settings.ratelimit_api_key_capacity,
                    refill_rate=settings.ratelimit_api_key_refill_rate,
                    description="Per-API key rate limit",
                ),
                RateLimitScope.TENANT: RateLimitConfig(
                    name="Tenant Rate Limit",
                    scope=RateLimitScope.TENANT,
                    capacity=settings.ratelimit_tenant_capacity,
                    refill_rate=settings.ratelimit_tenant_refill_rate,
                    description="Per-tenant rate limit",
                ),
                RateLimitScope.USER: RateLimitConfig(
                    name="User Rate Limit",
                    scope=RateLimitScope.USER,
                    capacity=settings.ratelimit_user_capacity,
                    refill_rate=settings.ratelimit_user_refill_rate,
                    description="Per-user rate limit",
                ),
                RateLimitScope.GLOBAL: RateLimitConfig(
                    name="Global Rate Limit",
                    scope=RateLimitScope.GLOBAL,
                    capacity=settings.ratelimit_global_capacity,
                    refill_rate=settings.ratelimit_global_refill_rate,
                    description="Global API rate limit",
                ),
            }

    async def _get_redis(self) -> aioredis.Redis | None:
        """Get or create Redis connection."""
        if self._redis is None:
            try:
                self._redis = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # Load Lua script
                self._script_sha = await self._redis.script_load(
                    self.TOKEN_BUCKET_SCRIPT
                )
                self._use_memory_fallback = False
                logger.info("rate_limiter_redis_connected", url=self.redis_url)
            except Exception as e:
                logger.warning(
                    "rate_limiter_redis_connection_failed",
                    error=str(e),
                    fallback="memory",
                )
                self._use_memory_fallback = True
                return None
        return self._redis

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._script_sha = None

    def _make_key(self, scope: RateLimitScope, identifier: str) -> str:
        """Create a Redis key for the rate limit bucket."""
        # Hash the identifier for consistent key length
        id_hash = hashlib.sha256(identifier.encode()).hexdigest()[:16]
        return f"{self.key_prefix}:{scope.value}:{id_hash}"

    def _get_config(self, scope: RateLimitScope, identifier: str) -> RateLimitConfig:
        """Get configuration for a scope, considering overrides."""
        base_config = self._configs.get(scope)
        if not base_config:
            # Return a permissive default
            return RateLimitConfig(
                name=f"Default {scope.value}",
                scope=scope,
                capacity=1000,
                refill_rate=100,
            )

        # Check for override
        override_key = f"{scope.value}:{identifier}"
        override = self._overrides.get(override_key)

        if override and override.enabled:
            # Check expiration
            if override.expires_at and override.expires_at < datetime.utcnow():
                del self._overrides[override_key]
            else:
                # Apply override
                return RateLimitConfig(
                    name=base_config.name,
                    scope=scope,
                    capacity=override.capacity or base_config.capacity,
                    refill_rate=override.refill_rate or base_config.refill_rate,
                    description=f"Overridden: {override.reason}",
                )

        return base_config

    async def _check_redis(
        self,
        key: str,
        config: RateLimitConfig,
        cost: int = 1,
    ) -> RateLimitResult:
        """Check rate limit using Redis."""
        redis = await self._get_redis()
        if not redis or not self._script_sha:
            return await self._check_memory(key, config, cost)

        now = time.time()
        ttl = int(config.capacity / config.refill_rate * 2) + 60  # TTL with buffer

        try:
            result = await redis.evalsha(
                self._script_sha,
                1,  # Number of keys
                key,
                config.capacity,
                config.refill_rate,
                now,
                cost,
                ttl,
            )

            allowed = bool(result[0])
            remaining = float(result[1])
            retry_after = float(result[2]) if not allowed else None

            # Calculate reset time
            tokens_needed = config.capacity - remaining
            seconds_to_full = tokens_needed / config.refill_rate
            reset_at = datetime.utcnow() + timedelta(seconds=seconds_to_full)

            return RateLimitResult(
                allowed=allowed,
                limit=config.capacity,
                remaining=int(remaining),
                reset_at=reset_at,
                retry_after=retry_after,
                scope=config.scope,
                key=key,
                cost=cost,
            )

        except Exception as e:
            logger.error("rate_limiter_redis_error", error=str(e), key=key)
            # Fall back to memory
            return await self._check_memory(key, config, cost)

    async def _check_memory(
        self,
        key: str,
        config: RateLimitConfig,
        cost: int = 1,
    ) -> RateLimitResult:
        """Check rate limit using in-memory fallback."""
        now = time.time()

        if key not in self._memory_buckets:
            self._memory_buckets[key] = {
                "tokens": config.capacity,
                "last_update": now,
            }

        bucket = self._memory_buckets[key]

        # Refill tokens
        elapsed = now - bucket["last_update"]
        tokens_to_add = elapsed * config.refill_rate
        bucket["tokens"] = min(config.capacity, bucket["tokens"] + tokens_to_add)
        bucket["last_update"] = now

        # Check and consume
        allowed = bucket["tokens"] >= cost
        remaining = bucket["tokens"]
        retry_after = None

        if allowed:
            bucket["tokens"] -= cost
            remaining = bucket["tokens"]
        else:
            retry_after = (cost - bucket["tokens"]) / config.refill_rate

        # Calculate reset time
        tokens_needed = config.capacity - remaining
        seconds_to_full = tokens_needed / config.refill_rate
        reset_at = datetime.utcnow() + timedelta(seconds=seconds_to_full)

        return RateLimitResult(
            allowed=allowed,
            limit=config.capacity,
            remaining=int(remaining),
            reset_at=reset_at,
            retry_after=retry_after,
            scope=config.scope,
            key=key,
            cost=cost,
        )

    async def check(
        self,
        scope: RateLimitScope,
        identifier: str,
        cost: int = 1,
        endpoint: str | None = None,
        method: str | None = None,
    ) -> RateLimitResult:
        """Check rate limit for a given scope and identifier.

        Args:
            scope: The rate limit scope (IP, API_KEY, TENANT, etc.)
            identifier: The unique identifier for this scope
            cost: Token cost for this request
            endpoint: Optional endpoint path for endpoint-specific limits
            method: Optional HTTP method

        Returns:
            RateLimitResult with allowed status and headers
        """
        config = self._get_config(scope, identifier)

        if not config.enabled:
            # Return permissive result if disabled
            return RateLimitResult(
                allowed=True,
                limit=config.capacity,
                remaining=config.capacity,
                reset_at=datetime.utcnow() + timedelta(hours=1),
                scope=scope,
                key="disabled",
                cost=cost,
            )

        # Check endpoint-specific limits
        if endpoint:
            endpoint_config = self._get_endpoint_config(endpoint, method)
            if endpoint_config:
                cost = endpoint_config.cost

        key = self._make_key(scope, identifier)
        result = await self._check_redis(key, config, cost)

        # Emit event if limit exceeded
        if not result.allowed:
            await self._emit_limit_exceeded(
                scope=scope,
                identifier=identifier,
                key=key,
                result=result,
                endpoint=endpoint,
                method=method,
            )

        return result

    async def check_multiple(
        self,
        checks: list[tuple[RateLimitScope, str]],
        cost: int = 1,
        endpoint: str | None = None,
        method: str | None = None,
    ) -> RateLimitResult:
        """Check multiple rate limits and return the most restrictive.

        Args:
            checks: List of (scope, identifier) tuples to check
            cost: Token cost for this request
            endpoint: Optional endpoint path
            method: Optional HTTP method

        Returns:
            The most restrictive RateLimitResult
        """
        results = []

        for scope, identifier in checks:
            if identifier:  # Skip if identifier is empty
                result = await self.check(
                    scope=scope,
                    identifier=identifier,
                    cost=cost,
                    endpoint=endpoint,
                    method=method,
                )
                results.append(result)

        if not results:
            # No checks performed, allow
            return RateLimitResult(
                allowed=True,
                limit=1000,
                remaining=1000,
                reset_at=datetime.utcnow() + timedelta(hours=1),
                scope=RateLimitScope.GLOBAL,
                key="none",
                cost=cost,
            )

        # Return first denied or most restrictive allowed
        denied = [r for r in results if not r.allowed]
        if denied:
            return denied[0]

        # Return the one with lowest remaining tokens
        return min(results, key=lambda r: r.remaining)

    def _get_endpoint_config(
        self,
        endpoint: str,
        method: str | None,
    ) -> EndpointRateLimit | None:
        """Get endpoint-specific rate limit config if exists."""
        for limit in self._endpoint_limits:
            if re.match(limit.path_pattern, endpoint):
                if method is None or method.upper() in limit.methods:
                    return limit
        return None

    def add_endpoint_limit(self, limit: EndpointRateLimit) -> None:
        """Add an endpoint-specific rate limit."""
        self._endpoint_limits.append(limit)

    def set_override(self, override: RateLimitOverride) -> None:
        """Set a rate limit override for a specific key."""
        key = f"{override.scope.value}:{override.key}"
        self._overrides[key] = override
        logger.info(
            "rate_limit_override_set",
            key=key,
            capacity=override.capacity,
            refill_rate=override.refill_rate,
            reason=override.reason,
        )

    def remove_override(self, scope: RateLimitScope, key: str) -> bool:
        """Remove a rate limit override."""
        override_key = f"{scope.value}:{key}"
        if override_key in self._overrides:
            del self._overrides[override_key]
            logger.info("rate_limit_override_removed", key=override_key)
            return True
        return False

    async def get_status(
        self,
        scope: RateLimitScope,
        identifier: str,
    ) -> RateLimitStatus:
        """Get current rate limit status for an entity."""
        config = self._get_config(scope, identifier)
        key = self._make_key(scope, identifier)

        redis = await self._get_redis()
        requests = 0

        if redis and not self._use_memory_fallback:
            try:
                bucket = await redis.hgetall(key)
                counter_key = f"{key}:requests"
                requests = int(await redis.get(counter_key) or 0)

                if bucket:
                    tokens = float(bucket.get("tokens", config.capacity))
                    last_update = float(bucket.get("last_update", time.time()))

                    # Calculate current tokens with refill
                    elapsed = time.time() - last_update
                    current_tokens = min(
                        config.capacity, tokens + elapsed * config.refill_rate
                    )

                    return RateLimitStatus(
                        key=key,
                        scope=scope,
                        current_tokens=current_tokens,
                        capacity=config.capacity,
                        refill_rate=config.refill_rate,
                        last_refill=datetime.fromtimestamp(last_update),
                        requests_in_window=requests,
                    )
            except Exception as e:
                logger.warning("rate_limiter_get_status_error", error=str(e))

        # Check memory buckets
        if key in self._memory_buckets:
            bucket = self._memory_buckets[key]
            tokens = bucket.get("tokens", config.capacity)
            last_update = bucket.get("last_update", time.time())

            # Calculate current tokens with refill
            elapsed = time.time() - last_update
            current_tokens = min(config.capacity, tokens + elapsed * config.refill_rate)

            return RateLimitStatus(
                key=key,
                scope=scope,
                current_tokens=current_tokens,
                capacity=config.capacity,
                refill_rate=config.refill_rate,
                last_refill=datetime.fromtimestamp(last_update),
                requests_in_window=requests,
            )

        # Return default status (no activity yet)
        return RateLimitStatus(
            key=key,
            scope=scope,
            current_tokens=config.capacity,
            capacity=config.capacity,
            refill_rate=config.refill_rate,
            last_refill=datetime.utcnow(),
            requests_in_window=requests,
        )

    async def reset(self, scope: RateLimitScope, identifier: str) -> bool:
        """Reset rate limit for a specific key."""
        key = self._make_key(scope, identifier)

        redis = await self._get_redis()
        if redis:
            try:
                await redis.delete(key, f"{key}:requests")
                logger.info("rate_limit_reset", key=key, scope=scope.value)
                return True
            except Exception as e:
                logger.error("rate_limit_reset_error", error=str(e), key=key)

        # Memory fallback
        if key in self._memory_buckets:
            del self._memory_buckets[key]
            return True

        return False

    async def _emit_limit_exceeded(
        self,
        scope: RateLimitScope,
        identifier: str,
        key: str,
        result: RateLimitResult,
        endpoint: str | None,
        method: str | None,
    ) -> None:
        """Emit an event when rate limit is exceeded."""
        event = RateLimitEvent(
            key=key,
            scope=scope,
            endpoint=endpoint or "unknown",
            method=method or "unknown",
            current_tokens=result.remaining,
            limit=result.limit,
        )

        for callback in self._on_limit_exceeded:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error("rate_limit_callback_error", error=str(e))

        logger.warning(
            "rate_limit_exceeded",
            scope=scope.value,
            key=key,
            endpoint=endpoint,
            remaining=result.remaining,
            limit=result.limit,
        )

    def on_limit_exceeded(self, callback: callable) -> None:
        """Register a callback for when rate limit is exceeded."""
        self._on_limit_exceeded.append(callback)

    def get_configs(self) -> dict[RateLimitScope, RateLimitConfig]:
        """Get all rate limit configurations."""
        return self._configs.copy()

    def update_config(
        self,
        scope: RateLimitScope,
        capacity: int | None = None,
        refill_rate: float | None = None,
        enabled: bool | None = None,
    ) -> RateLimitConfig:
        """Update a rate limit configuration."""
        config = self._configs.get(scope)
        if not config:
            raise ValueError(f"No configuration for scope: {scope}")

        if capacity is not None:
            config.capacity = capacity
        if refill_rate is not None:
            config.refill_rate = refill_rate
        if enabled is not None:
            config.enabled = enabled

        return config


# Global rate limiter instance
rate_limiter = RateLimiter()
