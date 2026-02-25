"""Demo data generator for Incident Copilot demonstrations."""

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import datetime, UTC
from typing import Any

import structlog

from ..models import (
    AILogSummary,
    ContextCard,
    DatadogContext,
    Deployment,
    GitHubContext,
    LogSummary,
    MetricSnapshot,
    PastIncident,
    RunbookLink,
)
from .scenarios import DEMO_SCENARIOS, get_scenario

logger = structlog.get_logger()


class DemoGenerator:
    """
    Generate realistic demo data for Incident Copilot.

    Simulates the full context assembly flow with configurable
    delays to demonstrate the real-time nature of the system.
    """

    def __init__(self, simulate_delays: bool = True):
        """
        Initialize the demo generator.

        Args:
            simulate_delays: If True, adds realistic delays to simulate
                           actual API calls to integrations.
        """
        self.simulate_delays = simulate_delays

    async def _delay(self, min_ms: int = 100, max_ms: int = 500) -> None:
        """Add a realistic delay if simulation is enabled."""
        if self.simulate_delays:
            delay = random.randint(min_ms, max_ms) / 1000
            await asyncio.sleep(delay)

    async def generate_context_card(
        self,
        scenario_id: str | None = None,
    ) -> ContextCard:
        """
        Generate a complete context card for a demo scenario.

        Args:
            scenario_id: Specific scenario ID, or None for random selection.

        Returns:
            A fully populated ContextCard.
        """
        # Select scenario
        if scenario_id:
            scenario = get_scenario(scenario_id)
            if not scenario:
                raise ValueError(f"Unknown scenario: {scenario_id}")
        else:
            scenario = random.choice(DEMO_SCENARIOS)

        logger.info("generating_demo_context", scenario_id=scenario["id"])
        start_time = datetime.now(UTC)

        # Simulate fetching data from various sources
        alert = scenario["alert"]

        # Build GitHub context
        await self._delay(200, 400)  # Simulate GitHub API call
        deployments = [
            Deployment(
                sha=d["sha"],
                short_sha=d["sha"][:7],
                message=d["message"],
                author=d["author"],
                timestamp=d["deployed_at"],
                files_changed=d.get("changed_files", []),
                url=d.get("pr_url"),
            )
            for d in scenario["deployments"]
        ]
        github_context = GitHubContext(
            repo=f"acme/{alert['service']}",
            recent_deploys=deployments,
            codeowners=[o["name"] for o in scenario.get("owners", [])],
        )

        # Build Datadog/CloudWatch context
        await self._delay(300, 600)  # Simulate log API call
        logs = scenario["logs"]
        log_summaries = [
            LogSummary(
                pattern=(
                    e["message"][:50] + "..."
                    if len(e["message"]) > 50
                    else e["message"]
                ),
                count=e["count"],
                level=e["level"],
                sample_message=e["message"],
                first_seen=e.get("first_seen"),
                last_seen=e.get("last_seen"),
            )
            for e in logs["top_errors"][:5]
        ]
        error_rate_str = str(alert["details"].get("error_rate", "5"))
        error_rate = float(error_rate_str.rstrip("%")) if error_rate_str else 5.0
        datadog_context = DatadogContext(
            service=alert["service"],
            log_summaries=log_summaries,
            metrics=MetricSnapshot(
                error_rate=error_rate,
                time_range_minutes=logs.get("time_range_minutes", 15),
            ),
        )

        # Build AI summary
        await self._delay(500, 1000)  # Simulate AI call
        ai_data = scenario["ai_summary"]
        ai_summary = AILogSummary(
            top_issues=ai_data["key_findings"],
            explanation=ai_data["summary"],
            likely_cause=(
                ai_data["key_findings"][0] if ai_data["key_findings"] else None
            ),
            suggested_actions=ai_data.get("suggested_runbooks", []),
        )

        # Build similar incidents
        await self._delay(100, 200)  # Simulate similarity search
        similar_incidents = [
            PastIncident(
                incident_id=si["id"],
                title=si["title"],
                service=alert["service"],
                resolution=si.get("resolution"),
                occurred_at=datetime.fromisoformat(
                    si["occurred_at"].replace("Z", "+00:00")
                ),
                similarity_score=si["similarity_score"],
            )
            for si in scenario.get("similar_incidents", [])
        ]

        # Build linked runbooks
        await self._delay(100, 200)  # Simulate runbook search
        linked_runbooks = [
            RunbookLink(
                title=rb["title"],
                url=rb["url"],
                source="demo",
                relevance_score=rb["relevance_score"],
            )
            for rb in scenario.get("runbooks", [])
        ]

        # Calculate total time
        total_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        # Build the context card
        context_card = ContextCard(
            incident_id=f"demo-{alert['id']}",
            title=alert["title"],
            service_name=alert["service"],
            severity=alert["severity"],
            triggered_at=alert["triggered_at"],
            alert_url=f"https://demo.pagerduty.com/incidents/{alert.get('pagerduty_incident_id', 'DEMO')}",
            github=github_context,
            datadog=datadog_context,
            ai_summary=ai_summary,
            similar_incidents=similar_incidents,
            runbooks=linked_runbooks,
            assembly_time_ms=total_ms,
            owners=[o["name"] for o in scenario.get("owners", [])],
        )

        logger.info(
            "demo_context_generated",
            scenario_id=scenario["id"],
            assembly_ms=total_ms,
        )

        return context_card

    async def stream_context_assembly(
        self,
        scenario_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream the context assembly process step by step.

        Yields status updates as each integration is "queried",
        useful for real-time UI updates during demos.

        Args:
            scenario_id: Specific scenario ID, or None for random selection.

        Yields:
            Status dictionaries with progress updates.
        """
        # Select scenario
        if scenario_id:
            scenario = get_scenario(scenario_id)
            if not scenario:
                raise ValueError(f"Unknown scenario: {scenario_id}")
        else:
            scenario = random.choice(DEMO_SCENARIOS)

        alert = scenario["alert"]
        start_time = datetime.now(UTC)

        yield {
            "step": "alert_received",
            "status": "received",
            "message": f"Alert received: {alert['title']}",
            "data": {"service": alert["service"], "severity": alert["severity"].value},
            "elapsed_ms": 0,
        }

        # Simulate parallel fetching (but report sequentially for demo clarity)
        await self._delay(150, 300)
        yield {
            "step": "github_started",
            "status": "fetching",
            "message": "Fetching recent deployments from GitHub...",
            "elapsed_ms": self._elapsed_ms(start_time),
        }

        await self._delay(200, 400)
        yield {
            "step": "github_complete",
            "status": "complete",
            "message": f"Found {len(scenario['deployments'])} recent deployments",
            "data": {
                "deployment_count": len(scenario["deployments"]),
                "latest_deploy": (
                    scenario["deployments"][0]["sha"][:7]
                    if scenario["deployments"]
                    else None
                ),
            },
            "elapsed_ms": self._elapsed_ms(start_time),
        }

        await self._delay(100, 200)
        yield {
            "step": "logs_started",
            "status": "fetching",
            "message": "Fetching error logs from log provider...",
            "elapsed_ms": self._elapsed_ms(start_time),
        }

        await self._delay(300, 500)
        logs = scenario["logs"]
        yield {
            "step": "logs_complete",
            "status": "complete",
            "message": f"Retrieved {logs['error_count']} errors, {logs['warning_count']} warnings",
            "data": {
                "error_count": logs["error_count"],
                "warning_count": logs["warning_count"],
            },
            "elapsed_ms": self._elapsed_ms(start_time),
        }

        await self._delay(100, 200)
        yield {
            "step": "ai_started",
            "status": "analyzing",
            "message": "AI analyzing logs and deployments...",
            "elapsed_ms": self._elapsed_ms(start_time),
        }

        await self._delay(600, 1200)
        yield {
            "step": "ai_complete",
            "status": "complete",
            "message": "AI analysis complete",
            "data": {
                "confidence": scenario["ai_summary"]["confidence"],
                "finding_count": len(scenario["ai_summary"]["key_findings"]),
            },
            "elapsed_ms": self._elapsed_ms(start_time),
        }

        # Similarity search
        if scenario.get("similar_incidents"):
            await self._delay(100, 200)
            yield {
                "step": "similarity_complete",
                "status": "complete",
                "message": f"Found {len(scenario['similar_incidents'])} similar past incidents",
                "data": {"similar_count": len(scenario["similar_incidents"])},
                "elapsed_ms": self._elapsed_ms(start_time),
            }

        # Runbook linking
        if scenario.get("runbooks"):
            await self._delay(100, 150)
            yield {
                "step": "runbooks_complete",
                "status": "complete",
                "message": f"Linked {len(scenario['runbooks'])} relevant runbooks",
                "data": {"runbook_count": len(scenario["runbooks"])},
                "elapsed_ms": self._elapsed_ms(start_time),
            }

        # Final context card
        context_card = await self.generate_context_card(scenario["id"])

        yield {
            "step": "complete",
            "status": "delivered",
            "message": "Context card assembled and ready",
            "data": {"context_card": context_card.model_dump(mode="json")},
            "elapsed_ms": self._elapsed_ms(start_time),
        }

    def _elapsed_ms(self, start_time: datetime) -> int:
        """Calculate elapsed milliseconds since start."""
        return int((datetime.now(UTC) - start_time).total_seconds() * 1000)


# Convenience functions
async def generate_demo_card(scenario_id: str | None = None) -> ContextCard:
    """Generate a demo context card (convenience function)."""
    generator = DemoGenerator()
    return await generator.generate_context_card(scenario_id)


async def stream_demo(scenario_id: str | None = None) -> AsyncIterator[dict[str, Any]]:
    """Stream demo context assembly (convenience function)."""
    generator = DemoGenerator()
    async for update in generator.stream_context_assembly(scenario_id):
        yield update
