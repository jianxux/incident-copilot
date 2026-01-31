"""Demo mode API routes for Incident Copilot."""

import json
from typing import Annotated

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..demo import DemoGenerator, DEMO_SCENARIOS
from ..demo.scenarios import list_scenarios

logger = structlog.get_logger()

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/scenarios")
async def get_scenarios():
    """
    List available demo scenarios.
    
    Returns a list of scenarios that can be used to generate
    demo context cards for demonstrations.
    """
    return {
        "scenarios": list_scenarios(),
        "count": len(DEMO_SCENARIOS),
    }


@router.get("/scenarios/{scenario_id}")
async def get_scenario_details(scenario_id: str):
    """
    Get full details for a specific scenario.
    
    Returns the complete scenario definition including alert details,
    expected logs, deployments, and AI analysis.
    """
    from ..demo.scenarios import get_scenario

    scenario = get_scenario(scenario_id)
    if not scenario:
        return {"error": f"Scenario '{scenario_id}' not found"}, 404

    # Convert enums and datetimes for JSON serialization
    return _serialize_scenario(scenario)


@router.post("/trigger")
async def trigger_demo_incident(
    scenario_id: Annotated[str | None, Query(description="Specific scenario to trigger")] = None,
    simulate_delays: Annotated[bool, Query(description="Add realistic API delays")] = True,
):
    """
    Trigger a demo incident and return the assembled context card.
    
    This simulates the full incident flow:
    1. Alert received from PagerDuty/Opsgenie
    2. GitHub deployments fetched
    3. Logs fetched from Datadog/CloudWatch
    4. AI analysis performed
    5. Similar incidents searched
    6. Runbooks linked
    7. Context card assembled
    
    Args:
        scenario_id: Specific scenario ID, or None for random selection.
        simulate_delays: If True, adds realistic delays (~2-3s total).
        
    Returns:
        Complete context card as JSON.
    """
    logger.info("demo_trigger_requested", scenario_id=scenario_id)

    generator = DemoGenerator(simulate_delays=simulate_delays)
    context_card = await generator.generate_context_card(scenario_id)

    return {
        "status": "success",
        "demo_mode": True,
        "context_card": context_card.model_dump(mode="json"),
    }


@router.get("/trigger/stream")
async def trigger_demo_incident_stream(
    scenario_id: Annotated[str | None, Query(description="Specific scenario to trigger")] = None,
):
    """
    Trigger a demo incident with streaming progress updates.
    
    Returns Server-Sent Events (SSE) with progress updates as each
    integration is queried. Useful for real-time UI demonstrations.
    
    Event types:
    - alert_received: Initial alert data
    - github_started/complete: Deployment fetch progress
    - logs_started/complete: Log fetch progress
    - ai_started/complete: AI analysis progress
    - similarity_complete: Similar incident search results
    - runbooks_complete: Runbook linking results
    - complete: Final context card
    """
    logger.info("demo_stream_requested", scenario_id=scenario_id)

    async def event_stream():
        generator = DemoGenerator(simulate_delays=True)
        async for update in generator.stream_context_assembly(scenario_id):
            # Format as SSE
            event_type = update.get("step", "update")
            data = json.dumps(update)
            yield f"event: {event_type}\ndata: {data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/slack-preview")
async def preview_slack_message(
    scenario_id: Annotated[str | None, Query(description="Specific scenario")] = None,
):
    """
    Generate a preview of the Slack message that would be sent.
    
    Returns the formatted Slack blocks that would be delivered
    to the incidents channel, without actually sending.
    """
    from ..delivery.slack import SlackDelivery
    from ..config import get_settings

    generator = DemoGenerator(simulate_delays=False)
    context_card = await generator.generate_context_card(scenario_id)

    # Get Slack blocks without sending
    settings = get_settings()
    slack = SlackDelivery(settings)
    blocks = slack._build_context_blocks(context_card)

    return {
        "demo_mode": True,
        "channel": settings.slack_default_channel,
        "blocks": blocks,
        "text_fallback": f"🚨 {context_card.title}",
    }


def _serialize_scenario(scenario: dict) -> dict:
    """Serialize scenario for JSON response."""
    from datetime import datetime
    from ..models import Severity

    def convert(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Severity):
            return obj.value
        elif isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(i) for i in obj]
        return obj

    return convert(scenario)
