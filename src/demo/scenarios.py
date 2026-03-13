"""Realistic demo scenarios for Incident Copilot demonstrations."""

from datetime import UTC, datetime, timedelta
from typing import Any

from ..models import Severity


def _now() -> datetime:
    """Current time for scenario generation."""
    return datetime.now(UTC)


def _minutes_ago(minutes: int) -> datetime:
    """Time N minutes ago."""
    return _now() - timedelta(minutes=minutes)


# Demo scenario definitions
DEMO_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "demo-stripe-timeout",
        "name": "Payment Processing Timeout",
        "description": "High-severity incident with clear deployment correlation",
        "alert": {
            "id": "demo-alert-001",
            "title": "payments-api: High Error Rate (>5%)",
            "description": "Error rate exceeded 5% threshold for payments-api service",
            "service": "payments-api",
            "severity": Severity.HIGH,
            "triggered_at": _minutes_ago(3),
            "status": "triggered",
            "source": "pagerduty",
            "pagerduty_incident_id": "DEMO123",
            "details": {
                "error_rate": "7.3%",
                "normal_rate": "0.2%",
                "affected_endpoints": ["/v1/charges", "/v1/refunds"],
            },
        },
        "deployments": [
            {
                "sha": "abc1234",
                "message": "feat: Add retry logic for Stripe API calls",
                "author": "sarah.chen",
                "author_avatar": "https://avatars.githubusercontent.com/u/12345?v=4",
                "deployed_at": _minutes_ago(15),
                "pr_number": 847,
                "pr_url": "https://github.com/acme/payments-api/pull/847",
                "changed_files": [
                    "src/stripe/client.py",
                    "src/stripe/retry.py",
                    "tests/test_stripe.py",
                ],
            },
            {
                "sha": "def5678",
                "message": "chore: Bump stripe-python to 8.0.0",
                "author": "mike.johnson",
                "author_avatar": "https://avatars.githubusercontent.com/u/67890?v=4",
                "deployed_at": _minutes_ago(45),
                "pr_number": 845,
                "pr_url": "https://github.com/acme/payments-api/pull/845",
                "changed_files": ["requirements.txt", "pyproject.toml"],
            },
        ],
        "logs": {
            "error_count": 1459,
            "warning_count": 3241,
            "time_range_minutes": 15,
            "top_errors": [
                {
                    "message": "ConnectionTimeout: stripe-api.com:443 timed out after 30s",
                    "count": 847,
                    "level": "ERROR",
                    "first_seen": _minutes_ago(12),
                    "last_seen": _minutes_ago(1),
                },
                {
                    "message": "RetryExhausted: Max retries (3) exceeded for /v1/charges",
                    "count": 612,
                    "level": "ERROR",
                    "first_seen": _minutes_ago(10),
                    "last_seen": _minutes_ago(1),
                },
            ],
            "sample_logs": [
                {
                    "timestamp": _minutes_ago(5),
                    "level": "ERROR",
                    "message": "ConnectionTimeout: stripe-api.com:443 timed out after 30s",
                    "trace_id": "trace-abc123",
                    "request_id": "req-xyz789",
                },
                {
                    "timestamp": _minutes_ago(4),
                    "level": "ERROR",
                    "message": "RetryExhausted: Max retries (3) exceeded for /v1/charges",
                    "trace_id": "trace-def456",
                    "customer_id": "cus_demo123",
                },
            ],
        },
        "ai_summary": {
            "summary": """The payments-api service is experiencing widespread connection timeouts when communicating with Stripe's API. This started approximately 12 minutes ago.

**Root Cause Hypothesis:**
The recent deployment (abc1234, 15 minutes ago) introduced new retry logic for Stripe API calls. The implementation may have a configuration issue - the retry backoff appears too aggressive, causing a thundering herd effect when Stripe rate limits kick in.

**Evidence:**
- 847 connection timeouts to stripe-api.com in the last 15 minutes
- 612 retry exhaustion errors, suggesting the new retry logic is being triggered
- Timing correlates with deployment abc1234 by @sarah.chen

**Recommended Actions:**
1. Check if Stripe is reporting degraded service on their status page
2. Review the retry configuration in PR #847 - backoff multiplier may be too low
3. Consider rolling back deployment abc1234 if Stripe status is healthy
4. Monitor the Stripe API dashboard for rate limit hits""",
            "confidence": 0.87,
            "key_findings": [
                "Connection timeouts to Stripe API (847 occurrences)",
                "Retry exhaustion errors following recent retry logic deployment",
                "Strong correlation with 15-minute-old deployment",
            ],
            "suggested_runbooks": [
                "stripe-api-troubleshooting",
                "payments-rollback-procedure",
            ],
        },
        "similar_incidents": [
            {
                "id": "INC-2024-0892",
                "title": "Stripe API Timeouts - Rate Limiting",
                "occurred_at": "2024-11-15T14:30:00Z",
                "resolution": "Stripe had a partial outage. Waited for recovery.",
                "mttr_minutes": 45,
                "similarity_score": 0.91,
            },
            {
                "id": "INC-2024-0567",
                "title": "Payment Processing Degraded After Deploy",
                "occurred_at": "2024-09-22T09:15:00Z",
                "resolution": "Rolled back faulty retry configuration.",
                "mttr_minutes": 12,
                "similarity_score": 0.84,
            },
        ],
        "runbooks": [
            {
                "id": "rb-stripe-001",
                "title": "Stripe API Troubleshooting Guide",
                "url": "https://docs.acme.com/runbooks/stripe-api-troubleshooting",
                "relevance_score": 0.93,
            },
            {
                "id": "rb-payments-002",
                "title": "Payments Service Rollback Procedure",
                "url": "https://docs.acme.com/runbooks/payments-rollback",
                "relevance_score": 0.78,
            },
        ],
        "owners": [
            {"name": "Sarah Chen", "slack_id": "U012ABC", "role": "Primary"},
            {"name": "Mike Johnson", "slack_id": "U034DEF", "role": "Secondary"},
        ],
    },
    {
        "id": "demo-database-connection",
        "name": "Database Connection Pool Exhausted",
        "description": "Critical database incident with cascading failures",
        "alert": {
            "id": "demo-alert-002",
            "title": "user-service: Database Connection Pool Exhausted",
            "description": "Connection pool at 100% utilization, requests failing",
            "service": "user-service",
            "severity": Severity.CRITICAL,
            "triggered_at": _minutes_ago(5),
            "status": "triggered",
            "source": "pagerduty",
            "pagerduty_incident_id": "DEMO456",
            "details": {
                "pool_size": 100,
                "active_connections": 100,
                "waiting_requests": 847,
            },
        },
        "deployments": [
            {
                "sha": "ghi9012",
                "message": "feat: Add user analytics dashboard endpoint",
                "author": "alex.rivera",
                "author_avatar": "https://avatars.githubusercontent.com/u/11111?v=4",
                "deployed_at": _minutes_ago(30),
                "pr_number": 234,
                "pr_url": "https://github.com/acme/user-service/pull/234",
                "changed_files": [
                    "src/api/analytics.py",
                    "src/queries/user_stats.py",
                ],
            },
        ],
        "logs": {
            "error_count": 2341,
            "warning_count": 1892,
            "time_range_minutes": 15,
            "top_errors": [
                {
                    "message": "ConnectionPoolExhausted: No available connections in pool",
                    "count": 1247,
                    "level": "ERROR",
                    "first_seen": _minutes_ago(8),
                    "last_seen": _minutes_ago(1),
                },
                {
                    "message": "QueryTimeout: SELECT * FROM users WHERE ... exceeded 30s",
                    "count": 892,
                    "level": "ERROR",
                    "first_seen": _minutes_ago(10),
                    "last_seen": _minutes_ago(1),
                },
            ],
            "sample_logs": [
                {
                    "timestamp": _minutes_ago(3),
                    "level": "ERROR",
                    "message": "ConnectionPoolExhausted: No available connections in pool",
                    "endpoint": "/api/v1/analytics/dashboard",
                    "request_id": "req-pool-123",
                },
            ],
        },
        "ai_summary": {
            "summary": """**CRITICAL:** The user-service database connection pool is completely exhausted, causing cascading failures across the service.

**Root Cause:**
The new analytics dashboard endpoint (deployed 30 minutes ago by @alex.rivera) appears to be running expensive, long-running queries without proper pagination or caching. Each request holds a connection for 30+ seconds.

**Evidence:**
- 100/100 connections in use
- 847 requests waiting for connections
- 892 query timeouts on analytics-related queries
- All errors originate from the /api/v1/analytics/dashboard endpoint

**Immediate Actions Required:**
1. **Disable the analytics endpoint immediately** (feature flag or nginx block)
2. Kill long-running queries: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE '%user_stats%' AND state = 'active';`
3. Increase pool size temporarily if possible
4. Page the database team for support

**Post-Incident:**
- Review analytics queries for missing indexes
- Add query timeouts and connection limits per endpoint
- Implement caching for analytics data""",
            "confidence": 0.94,
            "key_findings": [
                "Connection pool 100% exhausted",
                "Long-running analytics queries holding connections",
                "Clear correlation with recent analytics endpoint deploy",
            ],
            "suggested_runbooks": [
                "database-connection-pool",
                "emergency-endpoint-disable",
            ],
        },
        "similar_incidents": [
            {
                "id": "INC-2024-0234",
                "title": "DB Pool Exhaustion - Report Generation",
                "occurred_at": "2024-08-10T16:45:00Z",
                "resolution": "Disabled report endpoint, optimized queries",
                "mttr_minutes": 8,
                "similarity_score": 0.96,
            },
        ],
        "runbooks": [
            {
                "id": "rb-db-001",
                "title": "Database Connection Pool Emergency Response",
                "url": "https://docs.acme.com/runbooks/db-connection-pool",
                "relevance_score": 0.97,
            },
        ],
        "owners": [
            {"name": "Alex Rivera", "slack_id": "U056GHI", "role": "Primary"},
            {"name": "Database Team", "slack_id": "C089JKL", "role": "Escalation"},
        ],
    },
    {
        "id": "demo-memory-leak",
        "name": "Memory Leak After Node.js Upgrade",
        "description": "Gradual memory leak causing OOM kills",
        "alert": {
            "id": "demo-alert-003",
            "title": "order-service: High Memory Usage (>90%)",
            "description": "Memory usage above 90% threshold, OOM kills detected",
            "service": "order-service",
            "severity": Severity.MEDIUM,
            "triggered_at": _minutes_ago(20),
            "status": "triggered",
            "source": "opsgenie",
            "opsgenie_alert_id": "demo-ops-789",
            "details": {
                "memory_usage_percent": 94,
                "oom_kills_last_hour": 3,
                "pods_restarting": ["order-service-abc123", "order-service-def456"],
            },
        },
        "deployments": [
            {
                "sha": "jkl3456",
                "message": "chore: Upgrade Node.js from 18 to 20",
                "author": "devops-bot",
                "deployed_at": _minutes_ago(180),  # 3 hours ago
                "pr_number": 567,
                "pr_url": "https://github.com/acme/order-service/pull/567",
                "changed_files": ["Dockerfile", ".nvmrc", "package.json"],
            },
        ],
        "logs": {
            "error_count": 156,
            "warning_count": 892,
            "time_range_minutes": 60,
            "top_errors": [
                {
                    "message": "FATAL ERROR: CALL_AND_RETRY_LAST Allocation failed - JavaScript heap out of memory",
                    "count": 12,
                    "level": "ERROR",
                    "first_seen": _minutes_ago(45),
                    "last_seen": _minutes_ago(5),
                },
            ],
            "sample_logs": [
                {
                    "timestamp": _minutes_ago(15),
                    "level": "WARNING",
                    "message": "Memory usage at 85%, approaching threshold",
                    "pod": "order-service-abc123",
                },
            ],
        },
        "ai_summary": {
            "summary": """The order-service is experiencing a memory leak that's causing periodic OOM kills. Memory usage is climbing steadily after the Node.js 20 upgrade 3 hours ago.

**Root Cause Hypothesis:**
The Node.js 18→20 upgrade may have introduced a memory leak, possibly related to:
- Changes in V8 garbage collection behavior
- A dependency incompatibility with Node.js 20
- Different default memory limits in Node.js 20

**Evidence:**
- Memory climbs from ~50% to 94% over ~1 hour, then OOM kill
- 3 OOM kills in the last hour
- Started after Node.js 20 upgrade (3 hours ago)

**Recommended Actions:**
1. Increase memory limits as temporary mitigation
2. Enable --max-old-space-size=4096 flag
3. Consider rolling back to Node.js 18
4. Run heap dump analysis: `kill -USR2 <pid>` to identify leak source

**Note:** This is a gradual leak, not an immediate emergency. You have time to investigate before the next OOM kill (~15-20 minutes at current rate).""",
            "confidence": 0.72,
            "key_findings": [
                "Memory leak causing OOM kills every ~60 minutes",
                "Correlates with Node.js 18→20 upgrade",
                "Gradual degradation, not sudden failure",
            ],
            "suggested_runbooks": ["nodejs-memory-debugging", "k8s-oom-response"],
        },
        "similar_incidents": [],
        "runbooks": [
            {
                "id": "rb-node-001",
                "title": "Node.js Memory Debugging Guide",
                "url": "https://docs.acme.com/runbooks/nodejs-memory",
                "relevance_score": 0.85,
            },
        ],
        "owners": [
            {"name": "Order Team", "slack_id": "C012MNO", "role": "Primary"},
        ],
    },
]


def get_scenario(scenario_id: str) -> dict[str, Any] | None:
    """Get a specific scenario by ID."""
    for scenario in DEMO_SCENARIOS:
        if scenario["id"] == scenario_id:
            return scenario
    return None


def list_scenarios() -> list[dict[str, str]]:
    """List available scenarios (without full data)."""
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "description": s["description"],
            "severity": s["alert"]["severity"].value,
        }
        for s in DEMO_SCENARIOS
    ]
