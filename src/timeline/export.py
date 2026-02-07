"""Timeline export for postmortems."""

import json
from enum import StrEnum

from .models import TimelineExport


class ExportFormat(StrEnum):
    """Supported export formats."""

    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"
    CSV = "csv"


class TimelineExporter:
    """Export timelines in various formats for postmortems."""

    def export(
        self,
        data: TimelineExport,
        format: ExportFormat = ExportFormat.MARKDOWN,
        include_metadata: bool = True,
        include_raw_data: bool = False,
    ) -> str:
        """Export timeline in specified format."""
        if format == ExportFormat.MARKDOWN:
            return self._export_markdown(data, include_metadata)
        elif format == ExportFormat.JSON:
            return self._export_json(data, include_raw_data)
        elif format == ExportFormat.HTML:
            return self._export_html(data, include_metadata)
        elif format == ExportFormat.CSV:
            return self._export_csv(data)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _export_markdown(self, data: TimelineExport, include_metadata: bool) -> str:
        """Export timeline as Markdown for postmortem documents."""
        lines = [
            f"# {data.title}",
            "",
            f"**Incident ID:** {data.incident_id}",
            f"**Exported:** {data.exported_at.strftime('%Y-%m-%d %H:%M UTC')}",
            "",
        ]

        # Summary section
        s = data.summary
        lines.extend(
            [
                "## Summary",
                "",
                f"- **Total Events:** {s.total_events}",
                f"- **Duration:** {self._format_duration(s.duration_seconds)}",
                f"- **First Event:** {s.first_event.strftime('%Y-%m-%d %H:%M:%S UTC') if s.first_event else 'N/A'}",
                f"- **Last Event:** {s.last_event.strftime('%Y-%m-%d %H:%M:%S UTC') if s.last_event else 'N/A'}",
                "",
            ]
        )

        # Event breakdown
        if s.event_counts_by_type:
            lines.extend(["### Events by Type", ""])
            for event_type, count in sorted(s.event_counts_by_type.items()):
                lines.append(f"- {event_type}: {count}")
            lines.append("")

        if s.event_counts_by_source:
            lines.extend(["### Events by Source", ""])
            for source, count in sorted(s.event_counts_by_source.items()):
                lines.append(f"- {source}: {count}")
            lines.append("")

        # Gaps section
        if s.gaps:
            lines.extend(["## Timeline Gaps", ""])
            lines.append("| Start | End | Duration | Severity |")
            lines.append("|-------|-----|----------|----------|")
            for gap in s.gaps:
                lines.append(
                    f"| {gap.start_time.strftime('%H:%M:%S')} | "
                    f"{gap.end_time.strftime('%H:%M:%S')} | "
                    f"{self._format_duration(gap.duration_seconds)} | "
                    f"{gap.severity} |"
                )
            lines.append("")

        # Timeline section
        lines.extend(["## Timeline", ""])

        current_date = None
        for entry in data.entries:
            event = entry.event
            event_date = event.timestamp.strftime("%Y-%m-%d")

            # Add date header if date changed
            if event_date != current_date:
                current_date = event_date
                lines.extend([f"### {current_date}", ""])

            # Format event
            icon = entry.icon or "•"
            milestone_marker = " ⭐" if entry.is_milestone else ""
            time_str = event.timestamp.strftime("%H:%M:%S")

            lines.append(f"#### {icon} {time_str} - {event.title}{milestone_marker}")
            lines.append("")

            if event.description:
                lines.append(f"{event.description}")
                lines.append("")

            if include_metadata:
                meta_parts = []
                if event.actor:
                    meta_parts.append(f"**Actor:** {event.actor}")
                meta_parts.append(f"**Source:** {event.source.value}")
                meta_parts.append(f"**Type:** {event.event_type.value}")
                if event.tags:
                    meta_parts.append(f"**Tags:** {', '.join(event.tags)}")

                lines.append(f"*{' | '.join(meta_parts)}*")
                lines.append("")

            if event.annotations:
                lines.append("**Annotations:**")
                for annotation in event.annotations:
                    lines.append(f"- {annotation}")
                lines.append("")

        return "\n".join(lines)

    def _export_json(self, data: TimelineExport, include_raw_data: bool) -> str:
        """Export timeline as JSON."""
        export_dict = {
            "incident_id": data.incident_id,
            "title": data.title,
            "exported_at": data.exported_at.isoformat(),
            "format_version": data.format_version,
            "summary": {
                "total_events": data.summary.total_events,
                "duration_seconds": data.summary.duration_seconds,
                "first_event": (
                    data.summary.first_event.isoformat()
                    if data.summary.first_event
                    else None
                ),
                "last_event": (
                    data.summary.last_event.isoformat()
                    if data.summary.last_event
                    else None
                ),
                "event_counts_by_type": data.summary.event_counts_by_type,
                "event_counts_by_source": data.summary.event_counts_by_source,
                "gaps": [
                    {
                        "start_time": g.start_time.isoformat(),
                        "end_time": g.end_time.isoformat(),
                        "duration_seconds": g.duration_seconds,
                        "severity": g.severity,
                    }
                    for g in data.summary.gaps
                ],
                "key_milestones": [str(m) for m in data.summary.key_milestones],
            },
            "events": [],
        }

        for entry in data.entries:
            event = entry.event
            event_dict = {
                "id": str(event.id),
                "timestamp": event.timestamp.isoformat(),
                "relative_time": entry.relative_time,
                "event_type": event.event_type.value,
                "source": event.source.value,
                "severity": event.severity.value,
                "title": event.title,
                "description": event.description,
                "actor": event.actor,
                "tags": event.tags,
                "annotations": event.annotations,
                "is_milestone": entry.is_milestone,
                "icon": entry.icon,
                "color": entry.color,
                "metadata": event.metadata,
            }
            if include_raw_data and event.raw_data:
                event_dict["raw_data"] = event.raw_data
            export_dict["events"].append(event_dict)

        return json.dumps(export_dict, indent=2, default=str)

    def _export_html(self, data: TimelineExport, include_metadata: bool) -> str:
        """Export timeline as HTML for web viewing."""
        html_parts = [
            "<!DOCTYPE html>",
            "<html><head>",
            f"<title>{data.title}</title>",
            "<style>",
            self._get_html_styles(),
            "</style>",
            "</head><body>",
            "<div class='container'>",
            f"<h1>{data.title}</h1>",
            f"<p class='meta'>Incident: {data.incident_id} | Exported: {data.exported_at.strftime('%Y-%m-%d %H:%M UTC')}</p>",
        ]

        # Summary
        s = data.summary
        html_parts.extend(
            [
                "<div class='summary'>",
                "<h2>Summary</h2>",
                "<div class='stats'>",
                f"<div class='stat'><span class='label'>Events</span><span class='value'>{s.total_events}</span></div>",
                f"<div class='stat'><span class='label'>Duration</span><span class='value'>{self._format_duration(s.duration_seconds)}</span></div>",
                f"<div class='stat'><span class='label'>Gaps</span><span class='value'>{len(s.gaps)}</span></div>",
                "</div></div>",
            ]
        )

        # Timeline
        html_parts.append("<div class='timeline'>")
        html_parts.append("<h2>Timeline</h2>")

        for entry in data.entries:
            event = entry.event
            milestone_class = " milestone" if entry.is_milestone else ""
            color = entry.color or "#3498db"

            html_parts.extend(
                [
                    f"<div class='event{milestone_class}' style='border-left-color: {color}'>",
                    "<div class='event-header'>",
                    f"<span class='icon'>{entry.icon or '•'}</span>",
                    f"<span class='time'>{event.timestamp.strftime('%H:%M:%S')}</span>",
                    f"<span class='relative'>({entry.relative_time})</span>",
                    "</div>",
                    f"<h3>{event.title}</h3>",
                ]
            )

            if event.description:
                html_parts.append(f"<p class='description'>{event.description}</p>")

            if include_metadata:
                html_parts.append("<div class='metadata'>")
                html_parts.append(
                    f"<span class='badge source'>{event.source.value}</span>"
                )
                html_parts.append(
                    f"<span class='badge type'>{event.event_type.value}</span>"
                )
                if event.actor:
                    html_parts.append(f"<span class='badge actor'>{event.actor}</span>")
                for tag in event.tags:
                    html_parts.append(f"<span class='badge tag'>{tag}</span>")
                html_parts.append("</div>")

            html_parts.append("</div>")

        html_parts.extend(["</div>", "</div>", "</body></html>"])
        return "\n".join(html_parts)

    def _export_csv(self, data: TimelineExport) -> str:
        """Export timeline as CSV."""
        lines = [
            "timestamp,relative_time,event_type,source,severity,title,description,actor,tags"
        ]

        for entry in data.entries:
            event = entry.event
            # Escape quotes in text fields
            title = event.title.replace('"', '""')
            desc = (event.description or "").replace('"', '""')
            actor = (event.actor or "").replace('"', '""')
            tags = ";".join(event.tags)

            lines.append(
                f"{event.timestamp.isoformat()},{entry.relative_time},"
                f"{event.event_type.value},{event.source.value},{event.severity.value},"
                f'"{title}","{desc}","{actor}","{tags}"'
            )

        return "\n".join(lines)

    def _format_duration(self, seconds: float | None) -> str:
        """Format duration in human-readable format."""
        if seconds is None:
            return "N/A"

        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        elif seconds < 86400:
            hours = seconds // 3600
            mins = (seconds % 3600) // 60
            return f"{hours}h {mins}m"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            return f"{days}d {hours}h"

    def _get_html_styles(self) -> str:
        """CSS styles for HTML export."""
        return """
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
            .container { max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            h1 { margin-top: 0; color: #2c3e50; }
            .meta { color: #7f8c8d; font-size: 14px; }
            .summary { background: #f8f9fa; padding: 20px; border-radius: 6px; margin: 20px 0; }
            .summary h2 { margin-top: 0; font-size: 18px; }
            .stats { display: flex; gap: 30px; }
            .stat { text-align: center; }
            .stat .label { display: block; color: #7f8c8d; font-size: 12px; text-transform: uppercase; }
            .stat .value { display: block; font-size: 24px; font-weight: bold; color: #2c3e50; }
            .timeline h2 { font-size: 18px; margin-bottom: 20px; }
            .event { border-left: 4px solid #3498db; padding: 15px 20px; margin-bottom: 15px; background: #fafafa; border-radius: 0 6px 6px 0; }
            .event.milestone { background: #fff9e6; }
            .event-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
            .icon { font-size: 18px; }
            .time { font-family: monospace; color: #2c3e50; font-weight: bold; }
            .relative { color: #7f8c8d; font-size: 12px; }
            .event h3 { margin: 0 0 8px 0; font-size: 16px; color: #2c3e50; }
            .description { margin: 0 0 10px 0; color: #555; line-height: 1.5; }
            .metadata { display: flex; flex-wrap: wrap; gap: 6px; }
            .badge { font-size: 11px; padding: 3px 8px; border-radius: 12px; background: #e9ecef; color: #495057; }
            .badge.source { background: #d1ecf1; color: #0c5460; }
            .badge.type { background: #d4edda; color: #155724; }
            .badge.actor { background: #e2d5f1; color: #4a2c7a; }
            .badge.tag { background: #fff3cd; color: #856404; }
        """
