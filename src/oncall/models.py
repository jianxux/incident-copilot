"""Models for on-call handoff summaries.

These models are intentionally lightweight and designed for API and delivery.
Persistence is currently in-memory (suitable for dev/test); in production this
should be backed by a database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HandoffDeliveryChannel(StrEnum):
    """Supported handoff delivery channels."""

    SLACK = "slack"
    TEAMS = "teams"
    EMAIL = "email"
    IN_APP = "in_app"


class ShiftPerson(BaseModel):
    """Minimal person info for handoff context."""

    id: str
    name: str
    email: str | None = None
    slack_user_id: str | None = None


class ShiftInfo(BaseModel):
    """Information about the outgoing and incoming shift."""

    schedule_id: str
    schedule_name: str | None = None

    outgoing: ShiftPerson | None = None
    incoming: ShiftPerson | None = None

    shift_start: datetime
    shift_end: datetime
    handoff_time: datetime

    timezone: str = "UTC"
    provider: str = "unknown"

    raw: dict[str, Any] = Field(default_factory=dict)


class IncidentActivityItem(BaseModel):
    """Incident-like activity used in handoff summaries."""

    id: str
    title: str
    status: str | None = None
    severity: str | None = None
    service: str | None = None
    url: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_at: datetime | None = None

    owner: str | None = None
    summary: str | None = None
    next_steps: list[str] = Field(default_factory=list)

    raw: dict[str, Any] = Field(default_factory=dict)


class HandoffMetrics(BaseModel):
    """Basic shift metrics."""

    incidents_opened: int = 0
    incidents_resolved: int = 0
    incidents_escalated: int = 0
    alerts_acknowledged_unresolved: int = 0


class HandoffAggregate(BaseModel):
    """Aggregated data for a shift window."""

    shift: ShiftInfo

    active_incidents: list[IncidentActivityItem] = Field(default_factory=list)
    resolved_incidents: list[IncidentActivityItem] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)

    metrics: HandoffMetrics = Field(default_factory=HandoffMetrics)

    data_sources: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class HandoffSummary(BaseModel):
    """Generated handoff summary (AI or heuristic)."""

    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    shift: ShiftInfo
    aggregate: HandoffAggregate

    title: str
    brief_markdown: str

    delivered_to: list[dict[str, Any]] = Field(default_factory=list)
    generator: str = "heuristic"
    model: str | None = None


class HandoffConfig(BaseModel):
    """Configuration for automatic handoff generation.

    This is stored in-memory currently.
    """

    schedule_id: str
    enabled: bool = False

    # How far after the handoff boundary we allow auto-generation.
    grace_minutes: int = Field(default=15, ge=0, le=180)

    # How far ahead we look for an upcoming handoff.
    lookahead_minutes: int = Field(default=60, ge=5, le=24 * 60)

    # Delivery preferences
    delivery_channels: list[HandoffDeliveryChannel] = Field(default_factory=list)

    # Where to send (per channel). For Slack, this should be a channel ID or user ID.
    slack_target: str | None = None
    teams_webhook_url: str | None = None
    email_target: str | None = None

    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
