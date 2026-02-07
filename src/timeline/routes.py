"""FastAPI routes for timeline viewing and management."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .models import (
    TimelineEvent,
    TimelineEntry,
    TimelineFilter,
    TimelineSummary,
    TimelineExport,
    EventType,
    EventSource,
    EventSeverity,
)
from .service import TimelineService, get_timeline_service
from .collectors import CompositeCollector, create_default_collector
from .export import TimelineExporter, ExportFormat


router = APIRouter(prefix="/timeline", tags=["timeline"])


# Request/Response models
class AddEventRequest(BaseModel):
    """Request to add a manual event."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: EventType = EventType.MANUAL
    severity: EventSeverity = EventSeverity.INFO
    title: str
    description: str | None = None
    actor: str | None = None
    tags: list[str] = Field(default_factory=list)


class AnnotateEventRequest(BaseModel):
    """Request to annotate an event."""

    annotation: str


class TagEventRequest(BaseModel):
    """Request to tag an event."""

    tags: list[str]


class LinkEventsRequest(BaseModel):
    """Request to link events."""

    related_ids: list[UUID]


class CollectEventsRequest(BaseModel):
    """Request to collect events from sources."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    sources: list[EventSource] | None = None


class ExportRequest(BaseModel):
    """Request to export timeline."""

    format: ExportFormat = ExportFormat.MARKDOWN
    title: str = "Incident Timeline"
    include_metadata: bool = True
    include_raw_data: bool = False


# Dependency
def get_service() -> TimelineService:
    return get_timeline_service()


def get_collector() -> CompositeCollector:
    return create_default_collector()


# Routes
@router.get("/{incident_id}", response_model=list[TimelineEntry])
async def get_timeline(
    incident_id: str,
    service: Annotated[TimelineService, Depends(get_service)],
    event_types: Annotated[list[EventType] | None, Query()] = None,
    sources: Annotated[list[EventSource] | None, Query()] = None,
    severities: Annotated[list[EventSeverity] | None, Query()] = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    actors: Annotated[list[str] | None, Query()] = None,
    tags: Annotated[list[str] | None, Query()] = None,
    search: str | None = None,
):
    """Get timeline for an incident with optional filtering."""
    filters = TimelineFilter(
        event_types=event_types,
        sources=sources,
        severities=severities,
        start_time=start_time,
        end_time=end_time,
        actors=actors,
        tags=tags,
        search_query=search,
    )
    return await service.get_timeline(incident_id, filters)


@router.get("/{incident_id}/summary", response_model=TimelineSummary)
async def get_timeline_summary(
    incident_id: str,
    service: Annotated[TimelineService, Depends(get_service)],
):
    """Get summary statistics for an incident timeline."""
    return await service.get_summary(incident_id)


@router.get("/{incident_id}/events/{event_id}", response_model=TimelineEvent)
async def get_event(
    incident_id: str,
    event_id: UUID,
    service: Annotated[TimelineService, Depends(get_service)],
):
    """Get a specific timeline event."""
    event = await service.get_event(incident_id, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("/{incident_id}/events", response_model=TimelineEvent)
async def add_event(
    incident_id: str,
    request: AddEventRequest,
    service: Annotated[TimelineService, Depends(get_service)],
):
    """Add a manual event to the timeline."""
    event = TimelineEvent(
        incident_id=incident_id,
        timestamp=request.timestamp,
        event_type=request.event_type,
        source=EventSource.MANUAL,
        severity=request.severity,
        title=request.title,
        description=request.description,
        actor=request.actor,
        tags=request.tags,
    )
    return await service.add_event(event)


@router.delete("/{incident_id}/events/{event_id}")
async def delete_event(
    incident_id: str,
    event_id: UUID,
    service: Annotated[TimelineService, Depends(get_service)],
):
    """Delete an event from the timeline."""
    deleted = await service.delete_event(incident_id, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "deleted", "event_id": str(event_id)}


@router.post("/{incident_id}/events/{event_id}/annotate", response_model=TimelineEvent)
async def annotate_event(
    incident_id: str,
    event_id: UUID,
    request: AnnotateEventRequest,
    service: Annotated[TimelineService, Depends(get_service)],
):
    """Add an annotation to an event."""
    event = await service.annotate_event(incident_id, event_id, request.annotation)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("/{incident_id}/events/{event_id}/tag", response_model=TimelineEvent)
async def tag_event(
    incident_id: str,
    event_id: UUID,
    request: TagEventRequest,
    service: Annotated[TimelineService, Depends(get_service)],
):
    """Add tags to an event."""
    event = await service.tag_event(incident_id, event_id, request.tags)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("/{incident_id}/events/{event_id}/link", response_model=TimelineEvent)
async def link_events(
    incident_id: str,
    event_id: UUID,
    request: LinkEventsRequest,
    service: Annotated[TimelineService, Depends(get_service)],
):
    """Link related events together."""
    event = await service.link_events(incident_id, event_id, request.related_ids)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("/{incident_id}/collect", response_model=list[TimelineEntry])
async def collect_events(
    incident_id: str,
    request: CollectEventsRequest,
    service: Annotated[TimelineService, Depends(get_service)],
    collector: Annotated[CompositeCollector, Depends(get_collector)],
):
    """Collect events from configured sources and add to timeline."""
    events = await collector.collect_all(
        incident_id=incident_id, start_time=request.start_time, end_time=request.end_time
    )
    return await service.reconstruct_timeline(incident_id, events)


@router.post("/{incident_id}/export")
async def export_timeline(
    incident_id: str,
    request: ExportRequest,
    service: Annotated[TimelineService, Depends(get_service)],
):
    """Export timeline for postmortem."""
    entries = await service.get_timeline(incident_id)
    summary = await service.get_summary(incident_id)

    if not entries:
        raise HTTPException(status_code=404, detail="No timeline events found")

    exporter = TimelineExporter()
    export_data = TimelineExport(
        incident_id=incident_id, title=request.title, summary=summary, entries=entries
    )

    content = exporter.export(
        export_data,
        format=request.format,
        include_metadata=request.include_metadata,
        include_raw_data=request.include_raw_data,
    )

    return {"incident_id": incident_id, "format": request.format.value, "content": content}


@router.get("/{incident_id}/visualization")
async def get_visualization_data(
    incident_id: str,
    service: Annotated[TimelineService, Depends(get_service)],
):
    """Get timeline data in visualization-friendly format."""
    entries = await service.get_timeline(incident_id)
    summary = await service.get_summary(incident_id)

    # Group events by time buckets for visualization
    buckets: dict[str, list[dict]] = {}
    for entry in entries:
        bucket_key = entry.event.timestamp.strftime("%Y-%m-%d %H:00")
        if bucket_key not in buckets:
            buckets[bucket_key] = []
        buckets[bucket_key].append({
            "id": str(entry.event.id),
            "timestamp": entry.event.timestamp.isoformat(),
            "type": entry.event.event_type.value,
            "source": entry.event.source.value,
            "title": entry.event.title,
            "icon": entry.icon,
            "color": entry.color,
            "is_milestone": entry.is_milestone,
            "relative_time": entry.relative_time,
        })

    return {
        "incident_id": incident_id,
        "summary": {
            "total_events": summary.total_events,
            "duration_seconds": summary.duration_seconds,
            "first_event": summary.first_event.isoformat() if summary.first_event else None,
            "last_event": summary.last_event.isoformat() if summary.last_event else None,
            "gaps_count": len(summary.gaps),
            "milestone_count": len(summary.key_milestones),
        },
        "event_counts": summary.event_counts_by_type,
        "source_counts": summary.event_counts_by_source,
        "time_buckets": buckets,
        "gaps": [
            {
                "start": gap.start_time.isoformat(),
                "end": gap.end_time.isoformat(),
                "duration_seconds": gap.duration_seconds,
                "severity": gap.severity,
            }
            for gap in summary.gaps
        ],
    }
