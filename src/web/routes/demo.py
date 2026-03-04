"""Demo generation routes and helpers."""

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request
from fastapi.responses import HTMLResponse

from ...models import (
    AILogSummary,
    ContextCard,
    DatadogContext,
    Deployment,
    GitHubContext,
    LogSummary,
    MetricSnapshot,
    Severity,
)
from ..store import incident_store
from .common import router, templates

# Demo data generation
DEMO_SERVICES = [
    "payments-api",
    "user-service",
    "notification-service",
    "checkout-api",
    "inventory-service",
]
DEMO_TITLES = [
    "High error rate detected",
    "Latency spike in production",
    "Database connection pool exhausted",
    "Memory usage critical",
    "Failed health checks",
    "Increased 5xx responses",
    "Queue processing delay",
    "Certificate expiring soon",
]


@router.post("/api/demo")
async def create_demo_incident():
    """Create a demo incident for testing."""
    return await enqueue_demo_incident()


async def enqueue_demo_incident() -> dict[str, str]:
    """Queue a demo incident and return initial processing status."""
    incident_id = str(uuid.uuid4())
    service = random.choice(DEMO_SERVICES)
    severity = random.choice(list(Severity))
    title = f"{random.choice(DEMO_TITLES)} in {service}"
    triggered_at = datetime.now(UTC)

    # Add incident in processing state
    await incident_store.add_incident(
        incident_id=incident_id,
        title=title,
        service_name=service,
        severity=severity,
        triggered_at=triggered_at,
    )

    # Simulate async processing
    asyncio.create_task(
        _process_demo_incident(incident_id, service, severity, title, triggered_at)
    )

    return {"incident_id": incident_id, "status": "processing"}


async def _process_demo_incident(
    incident_id: str,
    service: str,
    severity: Severity,
    title: str,
    triggered_at: datetime,
):
    """Simulate incident processing with demo data."""
    # Simulate processing time
    await asyncio.sleep(random.uniform(1.5, 3.5))

    # Randomly fail some incidents for realism
    if random.random() < 0.1:  # 10% failure rate
        await incident_store.fail_incident(
            incident_id,
            "Simulated failure: Could not fetch context from external services",
        )
        return

    # Generate demo context card
    now = datetime.now(UTC)

    # Demo deployments
    deploys = [
        Deployment(
            sha=f"{random.randint(0, 0xFFFFFFFF):08x}" * 5,
            short_sha=f"{random.randint(0, 0xFFFFFF):06x}",
            author=random.choice(["alice", "bob", "charlie", "diana"]),
            message=random.choice(
                [
                    "Fix connection pooling issue",
                    "Update dependencies",
                    "Add retry logic for external calls",
                    "Optimize database queries",
                    "Enable feature flag for new flow",
                ]
            ),
            timestamp=now - timedelta(hours=random.randint(1, 48)),
            files_changed=[f"src/{service.replace('-', '/')}/main.py"],
            additions=random.randint(10, 200),
            deletions=random.randint(5, 50),
        )
        for _ in range(random.randint(2, 5))
    ]

    github_ctx = GitHubContext(
        repo=f"mycompany/{service}",
        recent_deploys=deploys,
        codeowners=["@platform-team", "@oncall"],
    )

    # Demo Datadog context
    datadog_ctx = DatadogContext(
        service=service,
        logs=[],
        log_summaries=[
            LogSummary(
                pattern="Connection timeout to database",
                count=random.randint(50, 500),
                level="ERROR",
                sample_message="FATAL: connection to database 'prod-db' failed: timeout",
            ),
            LogSummary(
                pattern="Request processing slow",
                count=random.randint(100, 1000),
                level="WARN",
                sample_message="Request took 5234ms to complete",
            ),
        ],
        metrics=MetricSnapshot(
            error_rate=random.uniform(0.5, 15.0),
            error_rate_baseline=0.1,
            latency_p99_ms=random.uniform(200, 2000),
            request_count=random.randint(10000, 100000),
        ),
    )

    # Demo AI summary
    ai_summary = AILogSummary(
        top_issues=[
            "Database connection timeouts increased 10x in the last hour",
            "Error rate spiked following deployment abc123",
            "Memory pressure detected on primary database node",
        ],
        explanation="The service is experiencing elevated error rates primarily due to database connectivity issues. "
        "Connection pool exhaustion appears to be the root cause, possibly triggered by a recent deployment "
        "that increased query volume or changed connection handling.",
        likely_cause="Database connection pool exhaustion following increased traffic after deployment",
        suggested_actions=[
            "Check database connection pool settings and increase if needed",
            "Review recent deployment changes for connection handling modifications",
            "Consider enabling connection pooler (PgBouncer) if not already in use",
            "Scale database resources if connection limits are being hit",
        ],
    )

    # Create context card
    card = ContextCard(
        incident_id=incident_id,
        title=title,
        severity=severity,
        service_name=service,
        triggered_at=triggered_at,
        alert_url=f"https://pagerduty.com/incidents/{incident_id}",
        github=github_ctx,
        datadog=datadog_ctx,
        ai_summary=ai_summary,
        similar_incidents=[],
        owners=["@platform-team", "@oncall"],
        runbook_url=f"https://wiki.internal/runbooks/{service}",
        dashboard_url=f"https://datadog.com/dashboards/{service}",
        assembled_at=now,
        assembly_time_ms=random.randint(800, 2500),
        errors=[],
    )

    await incident_store.complete_incident(incident_id, card)


@router.get("/demo", response_class=HTMLResponse)
async def demo_page(request: Request):
    """Interactive demo page for showcasing Incident Copilot."""
    from ...demo.scenarios import list_scenarios

    scenarios = list_scenarios()

    return templates.TemplateResponse(
        "demo.html",
        {
            "request": request,
            "scenarios": scenarios,
            "page_title": "Demo Mode",
        },
    )
