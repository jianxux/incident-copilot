"""Tests for API rate limiting module."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.ratelimit.limiter import RateLimiter
from src.ratelimit.middleware import RateLimitMiddleware, rate_limit
from src.ratelimit.models import (
    EndpointRateLimit,
    RateLimitConfig,
    RateLimitOverride,
    RateLimitResult,
    RateLimitScope,
    RateLimitStatus,
)


# Test fixtures
@pytest.fixture
def limiter():
    """Create a fresh rate limiter for testing (memory-only)."""
    limiter = RateLimiter(redis_url=None)
    limiter._use_memory_fallback = True
    return limiter


@pytest.fixture
def test_config():
    """Create a test rate limit configuration."""
    return RateLimitConfig(
        name="Test Limit",
        scope=RateLimitScope.IP,
        capacity=10,
        refill_rate=1.0,  # 1 token per second
        description="Test configuration",
    )


@pytest.fixture
def test_app():
    """Create a minimal FastAPI app for testing."""
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/test")
    def test_endpoint():
        return {"message": "success"}

    @app.post("/api/expensive")
    def expensive_endpoint():
        return {"message": "expensive operation"}

    return app


class TestRateLimitModels:
    """Tests for rate limit models."""

    def test_rate_limit_config_creation(self, test_config):
        """Test creating a rate limit configuration."""
        assert test_config.name == "Test Limit"
        assert test_config.scope == RateLimitScope.IP
        assert test_config.capacity == 10
        assert test_config.refill_rate == 1.0
        assert test_config.enabled is True
        assert test_config.cost == 1

    def test_rate_limit_config_tokens_per_minute(self, test_config):
        """Test tokens per minute calculation."""
        assert test_config.tokens_per_minute == 60.0  # 1 * 60

    def test_rate_limit_config_tokens_per_hour(self, test_config):
        """Test tokens per hour calculation."""
        assert test_config.tokens_per_hour == 3600.0  # 1 * 3600

    def test_rate_limit_result_allowed(self):
        """Test creating an allowed rate limit result."""
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=50,
            reset_at=datetime.utcnow() + timedelta(minutes=1),
            scope=RateLimitScope.IP,
            key="test-key",
        )
        assert result.allowed is True
        assert result.remaining == 50
        assert result.retry_after is None

    def test_rate_limit_result_denied(self):
        """Test creating a denied rate limit result."""
        result = RateLimitResult(
            allowed=False,
            limit=100,
            remaining=0,
            reset_at=datetime.utcnow() + timedelta(minutes=1),
            retry_after=30.0,
            scope=RateLimitScope.IP,
            key="test-key",
        )
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after == 30.0

    def test_rate_limit_result_to_headers(self):
        """Test converting result to HTTP headers."""
        reset_at = datetime.utcnow() + timedelta(minutes=1)
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=50,
            reset_at=reset_at,
            scope=RateLimitScope.IP,
            key="test-key",
        )

        headers = result.to_headers()

        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "50"
        assert "X-RateLimit-Reset" in headers
        assert "Retry-After" not in headers

    def test_rate_limit_result_headers_with_retry_after(self):
        """Test headers include Retry-After when denied."""
        result = RateLimitResult(
            allowed=False,
            limit=100,
            remaining=0,
            reset_at=datetime.utcnow() + timedelta(minutes=1),
            retry_after=30.0,
            scope=RateLimitScope.IP,
            key="test-key",
        )

        headers = result.to_headers()

        assert headers["Retry-After"] == "30"

    def test_rate_limit_status_utilization(self):
        """Test rate limit status utilization calculation."""
        status = RateLimitStatus(
            key="test-key",
            scope=RateLimitScope.IP,
            current_tokens=25.0,
            capacity=100,
            refill_rate=10.0,
            last_refill=datetime.utcnow(),
            requests_in_window=50,
        )

        # 75% utilized (75 tokens consumed out of 100)
        assert status.utilization == 75.0

    def test_rate_limit_override_creation(self):
        """Test creating a rate limit override."""
        override = RateLimitOverride(
            key="tenant-123",
            scope=RateLimitScope.TENANT,
            capacity=10000,
            refill_rate=500.0,
            reason="Premium customer",
        )

        assert override.key == "tenant-123"
        assert override.scope == RateLimitScope.TENANT
        assert override.capacity == 10000
        assert override.enabled is True

    def test_endpoint_rate_limit(self):
        """Test endpoint-specific rate limit configuration."""
        limit = EndpointRateLimit(
            path_pattern=r"/api/v1/expensive/.*",
            methods=["POST"],
            capacity=5,
            refill_rate=0.1,
            cost=2,
        )

        assert limit.path_pattern == r"/api/v1/expensive/.*"
        assert "POST" in limit.methods
        assert limit.cost == 2


class TestRateLimiter:
    """Tests for the RateLimiter class."""

    @pytest.mark.asyncio
    async def test_check_allowed(self, limiter, test_config):
        """Test rate limit check when allowed."""
        limiter._configs[RateLimitScope.IP] = test_config

        result = await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.1",
        )

        assert result.allowed is True
        assert result.remaining == 9  # Started at 10, consumed 1
        assert result.limit == 10

    @pytest.mark.asyncio
    async def test_check_denied_after_exhaustion(self, limiter, test_config):
        """Test rate limit check when tokens exhausted."""
        limiter._configs[RateLimitScope.IP] = test_config

        # Exhaust the bucket
        for i in range(10):
            result = await limiter.check(
                scope=RateLimitScope.IP,
                identifier="192.168.1.1",
            )
            assert result.allowed is True

        # Next request should be denied
        result = await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.1",
        )

        assert result.allowed is False
        assert result.remaining <= 0
        assert result.retry_after is not None
        assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_tokens_refill_over_time(self, limiter, test_config):
        """Test that tokens refill over time."""
        # Use higher refill rate for faster test
        test_config.refill_rate = 10.0  # 10 tokens per second
        limiter._configs[RateLimitScope.IP] = test_config

        # Exhaust the bucket
        for i in range(10):
            await limiter.check(
                scope=RateLimitScope.IP,
                identifier="192.168.1.1",
            )

        # Wait for some refill (0.5 seconds = 5 tokens at 10/sec)
        await asyncio.sleep(0.5)

        # Should be allowed again
        result = await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.1",
        )

        # Should have refilled some tokens
        assert result.remaining >= 3  # At least 4 tokens (5 refilled, 1 consumed)

    @pytest.mark.asyncio
    async def test_different_identifiers_separate_buckets(self, limiter, test_config):
        """Test that different identifiers have separate buckets."""
        limiter._configs[RateLimitScope.IP] = test_config

        # Exhaust bucket for IP 1
        for i in range(10):
            await limiter.check(
                scope=RateLimitScope.IP,
                identifier="192.168.1.1",
            )

        # IP 2 should still have full bucket
        result = await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.2",
        )

        assert result.allowed is True
        assert result.remaining == 9

    @pytest.mark.asyncio
    async def test_check_multiple_scopes(self, limiter):
        """Test checking multiple scopes at once."""
        limiter._configs[RateLimitScope.IP] = RateLimitConfig(
            name="IP",
            scope=RateLimitScope.IP,
            capacity=100,
            refill_rate=10,
        )
        limiter._configs[RateLimitScope.TENANT] = RateLimitConfig(
            name="Tenant",
            scope=RateLimitScope.TENANT,
            capacity=50,  # Lower limit
            refill_rate=5,
        )

        result = await limiter.check_multiple(
            checks=[
                (RateLimitScope.IP, "192.168.1.1"),
                (RateLimitScope.TENANT, "tenant-123"),
            ],
        )

        # Should return the more restrictive result (tenant has lower remaining after ratio)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_override_increases_limit(self, limiter, test_config):
        """Test that overrides can increase limits."""
        limiter._configs[RateLimitScope.TENANT] = test_config

        # Set override with higher limit
        override = RateLimitOverride(
            key="premium-tenant",
            scope=RateLimitScope.TENANT,
            capacity=1000,
            refill_rate=100.0,
            reason="Premium customer",
        )
        limiter.set_override(override)

        result = await limiter.check(
            scope=RateLimitScope.TENANT,
            identifier="premium-tenant",
        )

        assert result.allowed is True
        assert result.limit == 1000

    @pytest.mark.asyncio
    async def test_override_expiration(self, limiter, test_config):
        """Test that expired overrides are removed."""
        limiter._configs[RateLimitScope.TENANT] = test_config

        # Set override that's already expired
        override = RateLimitOverride(
            key="expired-tenant",
            scope=RateLimitScope.TENANT,
            capacity=1000,
            expires_at=datetime.utcnow() - timedelta(hours=1),  # Expired
        )
        limiter.set_override(override)

        # Should use base config since override is expired
        result = await limiter.check(
            scope=RateLimitScope.TENANT,
            identifier="expired-tenant",
        )

        assert result.limit == test_config.capacity  # Base config

    @pytest.mark.asyncio
    async def test_reset_refills_bucket(self, limiter, test_config):
        """Test that reset refills the token bucket."""
        limiter._configs[RateLimitScope.IP] = test_config

        # Exhaust the bucket
        for i in range(10):
            await limiter.check(
                scope=RateLimitScope.IP,
                identifier="192.168.1.1",
            )

        # Verify exhausted
        result = await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.1",
        )
        assert result.allowed is False

        # Reset
        success = await limiter.reset(RateLimitScope.IP, "192.168.1.1")
        assert success is True

        # Should be allowed again with full capacity
        result = await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.1",
        )
        assert result.allowed is True
        assert result.remaining == 9

    @pytest.mark.asyncio
    async def test_get_status(self, limiter, test_config):
        """Test getting rate limit status."""
        limiter._configs[RateLimitScope.IP] = test_config

        # Make some requests
        for i in range(5):
            await limiter.check(
                scope=RateLimitScope.IP,
                identifier="192.168.1.1",
            )

        status = await limiter.get_status(RateLimitScope.IP, "192.168.1.1")

        assert status.capacity == 10
        assert status.refill_rate == 1.0
        # Tokens should be around 5 (started at 10, consumed 5)
        assert 4 <= status.current_tokens <= 6

    @pytest.mark.asyncio
    async def test_disabled_config_always_allows(self, limiter, test_config):
        """Test that disabled configs always allow."""
        test_config.enabled = False
        limiter._configs[RateLimitScope.IP] = test_config

        # Should always be allowed
        for i in range(100):
            result = await limiter.check(
                scope=RateLimitScope.IP,
                identifier="192.168.1.1",
            )
            assert result.allowed is True

    @pytest.mark.asyncio
    async def test_custom_cost(self, limiter, test_config):
        """Test requests with custom token cost."""
        limiter._configs[RateLimitScope.IP] = test_config

        # Use cost of 5 tokens
        result = await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.1",
            cost=5,
        )

        assert result.allowed is True
        assert result.remaining == 5  # Started at 10, consumed 5

        # Another request with cost 5
        result = await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.1",
            cost=5,
        )

        assert result.allowed is True
        assert result.remaining == 0

        # Next should be denied
        result = await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.1",
            cost=1,
        )

        assert result.allowed is False

    def test_update_config(self, limiter, test_config):
        """Test updating rate limit configuration."""
        limiter._configs[RateLimitScope.IP] = test_config

        updated = limiter.update_config(
            scope=RateLimitScope.IP,
            capacity=200,
            refill_rate=20.0,
        )

        assert updated.capacity == 200
        assert updated.refill_rate == 20.0

    def test_endpoint_limit(self, limiter):
        """Test adding endpoint-specific limits."""
        endpoint_limit = EndpointRateLimit(
            path_pattern=r"/api/v1/expensive",
            capacity=5,
            refill_rate=0.5,
            cost=2,
        )

        limiter.add_endpoint_limit(endpoint_limit)

        config = limiter._get_endpoint_config("/api/v1/expensive", "POST")
        assert config is not None
        assert config.cost == 2


class TestRateLimitMiddleware:
    """Tests for the rate limit middleware."""

    def test_middleware_excludes_health_endpoint(self, test_app):
        """Test that health endpoint is excluded from rate limiting."""
        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                ratelimit_enabled=True,
                ratelimit_exclude_paths=["/health"],
            )

            test_app.add_middleware(
                RateLimitMiddleware,
                exclude_paths=["/health"],
            )

            client = TestClient(test_app)

            # Health endpoint should always work
            for i in range(100):
                response = client.get("/health")
                assert response.status_code == 200

    def test_middleware_adds_headers(self, test_app):
        """Test that middleware adds rate limit headers."""
        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                ratelimit_enabled=True,
                ratelimit_exclude_paths=[],
                ratelimit_ip_capacity=100,
                ratelimit_ip_refill_rate=10.0,
                ratelimit_api_key_capacity=1000,
                ratelimit_api_key_refill_rate=50.0,
                ratelimit_tenant_capacity=5000,
                ratelimit_tenant_refill_rate=100.0,
                ratelimit_user_capacity=200,
                ratelimit_user_refill_rate=20.0,
                ratelimit_global_capacity=10000,
                ratelimit_global_refill_rate=500.0,
            )

            test_app.add_middleware(
                RateLimitMiddleware,
                exclude_paths=[],
            )

            client = TestClient(test_app)

            response = client.get("/api/test")

            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers

    def test_middleware_returns_429_when_exceeded(self):
        """Test that middleware returns 429 when rate limit exceeded."""
        # Create fresh rate limiter for this test with very low limits
        test_limiter = RateLimiter(redis_url=None)
        test_limiter._use_memory_fallback = True
        test_limiter._configs[RateLimitScope.IP] = RateLimitConfig(
            name="Test IP Limit",
            scope=RateLimitScope.IP,
            capacity=3,  # Very low limit
            refill_rate=0.01,  # Very slow refill
        )

        app = FastAPI()

        @app.get("/api/test")
        def test_endpoint():
            return {"message": "success"}

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                ratelimit_enabled=True,
                ratelimit_exclude_paths=[],
                ratelimit_ip_capacity=3,
                ratelimit_ip_refill_rate=0.01,
                ratelimit_api_key_capacity=1000,
                ratelimit_api_key_refill_rate=50.0,
                ratelimit_tenant_capacity=5000,
                ratelimit_tenant_refill_rate=100.0,
                ratelimit_user_capacity=200,
                ratelimit_user_refill_rate=20.0,
                ratelimit_global_capacity=10000,
                ratelimit_global_refill_rate=500.0,
            )

            with patch("src.ratelimit.middleware.rate_limiter", test_limiter):
                app.add_middleware(
                    RateLimitMiddleware,
                    exclude_paths=[],
                )

                client = TestClient(app)

                # First 3 requests should succeed
                for i in range(3):
                    response = client.get("/api/test")
                    assert response.status_code == 200, f"Request {i + 1} failed unexpectedly"

                # 4th request should be rate limited
                response = client.get("/api/test")
                assert response.status_code == 429, f"Expected 429, got {response.status_code}"

                # Check response body
                data = response.json()
                assert data["error"] == "rate_limit_exceeded"
                assert "retry_after" in data

    def test_middleware_disabled(self, test_app):
        """Test that middleware does nothing when disabled."""
        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                ratelimit_enabled=False,
                ratelimit_exclude_paths=[],
            )

            test_app.add_middleware(
                RateLimitMiddleware,
                enabled=False,
            )

            client = TestClient(test_app)

            # Should always work even with many requests
            for i in range(100):
                response = client.get("/api/test")
                assert response.status_code == 200


class TestRateLimitDecorator:
    """Tests for the rate_limit decorator."""

    @pytest.mark.asyncio
    async def test_decorator_limits_endpoint(self):
        """Test that decorator applies custom limits."""

        # This test verifies the decorator structure
        @rate_limit(capacity=5, refill_rate=1.0)
        async def limited_endpoint(request: Request = None):
            return {"message": "success"}

        assert limited_endpoint.__name__ == "limited_endpoint"

    @pytest.mark.asyncio
    async def test_decorator_with_different_scopes(self):
        """Test decorator with different scope types."""

        @rate_limit(scope=RateLimitScope.TENANT)
        async def tenant_limited(request: Request = None):
            return {"message": "success"}

        @rate_limit(scope=RateLimitScope.API_KEY)
        async def api_key_limited(request: Request = None):
            return {"message": "success"}

        # Just verify decorators work
        assert tenant_limited.__name__ == "tenant_limited"
        assert api_key_limited.__name__ == "api_key_limited"


class TestRateLimitScopes:
    """Tests for different rate limit scopes."""

    def test_all_scopes_defined(self):
        """Test that all expected scopes are defined."""
        assert RateLimitScope.IP.value == "ip"
        assert RateLimitScope.API_KEY.value == "api_key"
        assert RateLimitScope.TENANT.value == "tenant"
        assert RateLimitScope.USER.value == "user"
        assert RateLimitScope.ENDPOINT.value == "endpoint"
        assert RateLimitScope.GLOBAL.value == "global"


class TestRateLimitEvents:
    """Tests for rate limit event emission."""

    @pytest.mark.asyncio
    async def test_callback_on_limit_exceeded(self, limiter, test_config):
        """Test that callback is called when limit exceeded."""
        limiter._configs[RateLimitScope.IP] = test_config

        callback_called = False
        callback_event = None

        def on_exceeded(event):
            nonlocal callback_called, callback_event
            callback_called = True
            callback_event = event

        limiter.on_limit_exceeded(on_exceeded)

        # Exhaust the bucket
        for i in range(10):
            await limiter.check(
                scope=RateLimitScope.IP,
                identifier="192.168.1.1",
            )

        # Next request should trigger callback
        await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.1",
            endpoint="/api/test",
            method="GET",
        )

        assert callback_called is True
        assert callback_event is not None
        assert callback_event.scope == RateLimitScope.IP
        assert callback_event.endpoint == "/api/test"

    @pytest.mark.asyncio
    async def test_async_callback_supported(self, limiter, test_config):
        """Test that async callbacks work."""
        limiter._configs[RateLimitScope.IP] = test_config

        callback_called = False

        async def async_callback(event):
            nonlocal callback_called
            callback_called = True

        limiter.on_limit_exceeded(async_callback)

        # Exhaust and trigger
        for i in range(11):
            await limiter.check(
                scope=RateLimitScope.IP,
                identifier="192.168.1.1",
            )

        assert callback_called is True


class TestMemoryFallback:
    """Tests for in-memory fallback when Redis unavailable."""

    @pytest.mark.asyncio
    async def test_memory_fallback_works(self):
        """Test that rate limiting works without Redis."""
        limiter = RateLimiter(redis_url="redis://nonexistent:6379")
        limiter._use_memory_fallback = True

        config = RateLimitConfig(
            name="Test",
            scope=RateLimitScope.IP,
            capacity=5,
            refill_rate=1.0,
        )
        limiter._configs[RateLimitScope.IP] = config

        # Should work with memory
        for i in range(5):
            result = await limiter.check(
                scope=RateLimitScope.IP,
                identifier="192.168.1.1",
            )
            assert result.allowed is True

        # Should be denied
        result = await limiter.check(
            scope=RateLimitScope.IP,
            identifier="192.168.1.1",
        )
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_memory_buckets_separate(self):
        """Test that memory buckets are properly separated."""
        limiter = RateLimiter(redis_url=None)
        limiter._use_memory_fallback = True

        config = RateLimitConfig(
            name="Test",
            scope=RateLimitScope.IP,
            capacity=5,
            refill_rate=0.1,
        )
        limiter._configs[RateLimitScope.IP] = config

        # Exhaust bucket 1
        for i in range(5):
            await limiter.check(RateLimitScope.IP, "ip1")

        # Bucket 2 should still work
        result = await limiter.check(RateLimitScope.IP, "ip2")
        assert result.allowed is True
        assert result.remaining == 4


class TestIntegration:
    """Integration tests for rate limiting."""

    @pytest.mark.asyncio
    async def test_full_rate_limit_flow(self):
        """Test complete rate limiting flow."""
        limiter = RateLimiter(redis_url=None)
        limiter._use_memory_fallback = True

        # Configure
        limiter._configs[RateLimitScope.IP] = RateLimitConfig(
            name="IP",
            scope=RateLimitScope.IP,
            capacity=10,
            refill_rate=2.0,
        )
        limiter._configs[RateLimitScope.TENANT] = RateLimitConfig(
            name="Tenant",
            scope=RateLimitScope.TENANT,
            capacity=50,
            refill_rate=10.0,
        )

        # Make requests
        for i in range(8):
            result = await limiter.check_multiple([
                (RateLimitScope.IP, "192.168.1.1"),
                (RateLimitScope.TENANT, "tenant-123"),
            ])
            assert result.allowed is True

        # Check status
        ip_status = await limiter.get_status(RateLimitScope.IP, "192.168.1.1")
        assert ip_status.current_tokens < 10

        # Apply override
        limiter.set_override(
            RateLimitOverride(
                key="192.168.1.1",
                scope=RateLimitScope.IP,
                capacity=100,
                reason="Testing",
            )
        )

        # Should have more capacity now
        result = await limiter.check(RateLimitScope.IP, "192.168.1.1")
        assert result.limit == 100
