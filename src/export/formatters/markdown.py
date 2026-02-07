"""Markdown export formatter for documentation."""

from datetime import datetime
from typing import Any

from ..models import (
    ColumnConfig,
    ExportType,
    MarkdownOptions,
    RelatedDataConfig,
)


class MarkdownFormatter:
    """Formatter for Markdown exports."""

    def __init__(
        self,
        export_type: ExportType,
        columns: list[ColumnConfig] | None = None,
        options: MarkdownOptions | None = None,
        related_data: RelatedDataConfig | None = None,
    ):
        self.export_type = export_type
        self.columns = columns or []
        self.options = options or MarkdownOptions()
        self.related_data = related_data or RelatedDataConfig()

    def format(self, data: list[dict[str, Any]] | dict[str, Any]) -> str:
        """Format data as Markdown string."""
        if self.export_type == ExportType.INCIDENTS:
            return self.format_incidents(data if isinstance(data, list) else [data])
        elif self.export_type == ExportType.POSTMORTEMS:
            return self.format_postmortems(data if isinstance(data, list) else [data])
        elif self.export_type == ExportType.ANALYTICS:
            return self.format_analytics(data if isinstance(data, dict) else {})
        else:
            return self._format_generic(data if isinstance(data, list) else [data])

    def format_bytes(self, data: list[dict[str, Any]] | dict[str, Any]) -> bytes:
        """Format data as Markdown bytes."""
        md_string = self.format(data)
        return md_string.encode("utf-8")

    def _heading(self, text: str, level: int = 1) -> str:
        """Create a heading with the configured style."""
        if self.options.heading_style == "setext" and level <= 2:
            underline = "=" if level == 1 else "-"
            return f"{text}\n{underline * len(text)}\n"
        return f"{'#' * level} {text}\n"

    def _table(self, headers: list[str], rows: list[list[str]]) -> str:
        """Create a Markdown table."""
        if not headers or not rows:
            return ""

        # Header row
        header_row = "| " + " | ".join(headers) + " |"

        # Separator with alignment
        if self.options.table_alignment == "center":
            sep = "|" + "|".join(f":{'---':^}:" for _ in headers) + "|"
        elif self.options.table_alignment == "right":
            sep = "|" + "|".join(f" {'---':>}:" for _ in headers) + "|"
        else:  # left
            sep = "|" + "|".join(f":{'---':<} " for _ in headers) + "|"

        # Data rows
        data_rows = []
        for row in rows:
            # Escape pipe characters
            escaped = [str(cell).replace("|", "\\|") for cell in row]
            data_rows.append("| " + " | ".join(escaped) + " |")

        return "\n".join([header_row, sep] + data_rows) + "\n"

    def _code_block(self, code: str, language: str = "") -> str:
        """Create a code block."""
        if self.options.code_block_style == "indented":
            lines = code.split("\n")
            return "\n".join("    " + line for line in lines) + "\n"
        return f"```{language}\n{code}\n```\n"

    def _bullet_list(self, items: list[str], indent: int = 0) -> str:
        """Create a bullet list."""
        prefix = "  " * indent + "- "
        return "\n".join(prefix + item for item in items) + "\n"

    def _format_datetime(self, dt: datetime | str | None) -> str:
        """Format datetime for display."""
        if dt is None:
            return "N/A"
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except ValueError:
                return dt
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    def format_incidents(self, incidents: list[dict[str, Any]]) -> str:
        """Format incident data as Markdown."""
        lines = []

        # Title
        lines.append(self._heading("Incident Export", 1))

        # Metadata
        if self.options.include_metadata:
            lines.append(f"*Exported at: {datetime.utcnow().isoformat()}*\n")
            lines.append(f"*Total incidents: {len(incidents)}*\n\n")

        # Table of contents
        if self.options.include_toc and len(incidents) > 1:
            lines.append(self._heading("Table of Contents", 2))
            for incident in incidents:
                inc_id = incident.get("incident_id", "Unknown")
                title = incident.get("title", "Untitled")
                lines.append(f"- [{inc_id}: {title}](#{inc_id.lower()})\n")
            lines.append("\n")

        # Incident details
        lines.append(self._heading("Incidents", 2))

        for incident in incidents:
            lines.append(self._format_incident(incident))

        return "".join(lines)

    def _format_incident(self, incident: dict[str, Any]) -> str:
        """Format a single incident."""
        lines = []
        inc_id = incident.get("incident_id", "Unknown")
        title = incident.get("title", "Untitled")

        lines.append(self._heading(f"{inc_id}: {title}", 3))

        # Overview table
        lines.append(
            self._table(
                ["Field", "Value"],
                [
                    ["Severity", incident.get("severity", "N/A")],
                    ["Service", incident.get("service_name", "N/A")],
                    ["Status", incident.get("status", "N/A")],
                    ["Triggered", self._format_datetime(incident.get("triggered_at"))],
                    ["Resolved", self._format_datetime(incident.get("resolved_at"))],
                ],
            )
        )
        lines.append("\n")

        # Timeline
        if self.related_data.include_timeline:
            timeline = incident.get("timeline", [])
            if timeline:
                lines.append(self._heading("Timeline", 4))
                max_events = self.related_data.max_timeline_events
                display_timeline = timeline[:max_events] if max_events else timeline

                for event in display_timeline:
                    ts = self._format_datetime(event.get("timestamp"))
                    event_title = event.get("title", "Event")
                    event_type = event.get("event_type", "other")
                    lines.append(f"- **{ts}** - [{event_type}] {event_title}\n")

                if max_events and len(timeline) > max_events:
                    lines.append(
                        f"- *... and {len(timeline) - max_events} more events*\n"
                    )
                lines.append("\n")

        # Comments
        if self.related_data.include_comments:
            comments = incident.get("comments", [])
            if comments:
                lines.append(self._heading("Comments", 4))
                max_comments = self.related_data.max_comments
                display_comments = comments[:max_comments] if max_comments else comments

                for comment in display_comments:
                    author = comment.get("author", "Unknown")
                    text = comment.get("text", "")
                    ts = self._format_datetime(comment.get("created_at"))
                    lines.append(f"> **{author}** ({ts}):\n> {text}\n\n")
                lines.append("\n")

        lines.append("---\n\n")
        return "".join(lines)

    def format_postmortems(self, postmortems: list[dict[str, Any]]) -> str:
        """Format postmortem data as Markdown."""
        lines = []

        lines.append(self._heading("Postmortem Export", 1))

        if self.options.include_metadata:
            lines.append(f"*Exported at: {datetime.utcnow().isoformat()}*\n")
            lines.append(f"*Total postmortems: {len(postmortems)}*\n\n")

        if self.options.include_toc and len(postmortems) > 1:
            lines.append(self._heading("Table of Contents", 2))
            for pm in postmortems:
                pm_id = pm.get("id", "Unknown")
                title = pm.get("title", "Untitled")
                lines.append(f"- [{pm_id}: {title}](#{pm_id.lower()})\n")
            lines.append("\n")

        for pm in postmortems:
            lines.append(self._format_postmortem(pm))

        return "".join(lines)

    def _format_postmortem(self, pm: dict[str, Any]) -> str:
        """Format a single postmortem."""
        lines = []
        pm_id = pm.get("id", "Unknown")
        title = pm.get("title", "Untitled")

        lines.append(self._heading(f"{pm_id}: {title}", 2))

        # Overview
        lines.append(self._heading("Overview", 3))
        lines.append(
            self._table(
                ["Field", "Value"],
                [
                    ["Incident ID", pm.get("incident_id", "N/A")],
                    ["Service", pm.get("service_name", "N/A")],
                    ["Severity", pm.get("severity", "N/A")],
                    ["Status", pm.get("status", "N/A")],
                    [
                        "Duration",
                        f"{pm.get('incident_duration_minutes', 'N/A')} minutes",
                    ],
                    ["Created", self._format_datetime(pm.get("created_at"))],
                    ["Author", pm.get("created_by", "N/A")],
                ],
            )
        )
        lines.append("\n")

        # Executive Summary
        if pm.get("executive_summary"):
            lines.append(self._heading("Executive Summary", 3))
            lines.append(pm["executive_summary"] + "\n\n")

        # Root Cause
        if self.related_data.include_root_cause:
            root_cause = pm.get("root_cause", {})
            if root_cause:
                lines.append(self._heading("Root Cause Analysis", 3))
                lines.append(
                    f"**Primary Cause:** {root_cause.get('primary_cause', 'N/A')}\n\n"
                )

                if root_cause.get("trigger"):
                    lines.append(f"**Trigger:** {root_cause['trigger']}\n\n")

                factors = root_cause.get("contributing_factors", [])
                if factors:
                    lines.append("**Contributing Factors:**\n")
                    lines.append(self._bullet_list(factors))
                lines.append("\n")

        # Impact
        if self.related_data.include_impact:
            impact = pm.get("impact", {})
            if impact:
                lines.append(self._heading("Impact", 3))
                lines.append(
                    self._table(
                        ["Metric", "Value"],
                        [
                            ["Severity", impact.get("severity", "N/A")],
                            [
                                "Duration",
                                f"{impact.get('duration_minutes', 'N/A')} minutes",
                            ],
                            [
                                "Users Affected",
                                str(impact.get("users_affected", "N/A")),
                            ],
                            ["SLA Breach", "Yes" if impact.get("sla_breach") else "No"],
                        ],
                    )
                )

                services = impact.get("services_affected", [])
                if services:
                    lines.append("\n**Services Affected:**\n")
                    lines.append(self._bullet_list(services))
                lines.append("\n")

        # Timeline
        if self.related_data.include_timeline:
            timeline = pm.get("timeline", [])
            if timeline:
                lines.append(self._heading("Timeline", 3))
                max_events = self.related_data.max_timeline_events
                display_timeline = timeline[:max_events] if max_events else timeline

                for event in display_timeline:
                    ts = self._format_datetime(event.get("timestamp"))
                    event_title = event.get("title", "Event")
                    lines.append(f"- **{ts}**: {event_title}\n")
                lines.append("\n")

        # Action Items
        if self.related_data.include_action_items:
            actions = pm.get("action_items", [])
            if actions:
                lines.append(self._heading("Action Items", 3))
                lines.append(
                    self._table(
                        ["ID", "Title", "Priority", "Status", "Owner"],
                        [
                            [
                                a.get("id", ""),
                                a.get("title", ""),
                                a.get("priority", ""),
                                a.get("status", ""),
                                a.get("owner", "N/A"),
                            ]
                            for a in actions
                        ],
                    )
                )
                lines.append("\n")

        # Lessons Learned
        lessons = pm.get("lessons_learned", [])
        if lessons:
            lines.append(self._heading("Lessons Learned", 3))
            lines.append(self._bullet_list(lessons))
            lines.append("\n")

        lines.append("---\n\n")
        return "".join(lines)

    def format_analytics(self, analytics: dict[str, Any]) -> str:
        """Format analytics data as Markdown."""
        lines = []

        lines.append(self._heading("Analytics Report", 1))

        if self.options.include_metadata:
            lines.append(f"*Generated at: {datetime.utcnow().isoformat()}*\n\n")

        # MTTR Stats
        if "mttr_stats" in analytics:
            stats = analytics["mttr_stats"]
            lines.append(self._heading("MTTR Statistics", 2))
            lines.append(f"**Period:** {stats.get('period', 'N/A')}\n\n")
            lines.append(
                self._table(
                    ["Metric", "Value"],
                    [
                        [
                            "Mean MTTR",
                            (
                                f"{stats.get('mean_mttr_minutes', 'N/A'):.1f} minutes"
                                if stats.get("mean_mttr_minutes")
                                else "N/A"
                            ),
                        ],
                        [
                            "Median MTTR",
                            (
                                f"{stats.get('median_mttr_minutes', 'N/A'):.1f} minutes"
                                if stats.get("median_mttr_minutes")
                                else "N/A"
                            ),
                        ],
                        [
                            "P90 MTTR",
                            (
                                f"{stats.get('p90_mttr_minutes', 'N/A'):.1f} minutes"
                                if stats.get("p90_mttr_minutes")
                                else "N/A"
                            ),
                        ],
                        ["Total Incidents", str(stats.get("incidents_count", 0))],
                        ["Resolved", str(stats.get("resolved_count", 0))],
                    ],
                )
            )

            if stats.get("improvement_percent") is not None:
                trend = "📈" if stats["improvement_percent"] > 0 else "📉"
                lines.append(
                    f"\n{trend} **Trend:** {stats['improvement_percent']:.1f}% "
                    "compared to previous period\n"
                )
            lines.append("\n")

        # Severity Breakdown
        if "severity_breakdown" in analytics:
            lines.append(self._heading("Incidents by Severity", 2))
            breakdown = analytics["severity_breakdown"]
            lines.append(
                self._table(
                    ["Severity", "Count"],
                    [[sev, str(count)] for sev, count in breakdown.items()],
                )
            )
            lines.append("\n")

        # Service Breakdown
        if "service_breakdown" in analytics:
            lines.append(self._heading("Incidents by Service", 2))
            breakdown = analytics["service_breakdown"]
            lines.append(
                self._table(
                    ["Service", "Count"],
                    [[svc, str(count)] for svc, count in breakdown.items()],
                )
            )
            lines.append("\n")

        # Period Comparison
        if "comparison" in analytics:
            comp = analytics["comparison"]
            lines.append(self._heading("Period Comparison", 2))
            trend_emoji = {"improving": "✅", "degrading": "⚠️", "stable": "➡️"}
            lines.append(
                f"**Trend:** {trend_emoji.get(comp.get('trend', 'stable'), '')} "
                f"{comp.get('trend', 'stable').title()}\n\n"
            )
            if comp.get("mttr_change_percent") is not None:
                lines.append(f"**MTTR Change:** {comp['mttr_change_percent']:.1f}%\n")
            lines.append("\n")

        return "".join(lines)

    def _format_generic(self, data: list[dict[str, Any]]) -> str:
        """Format generic list data as Markdown table."""
        if not data:
            return "*No data to export*\n"

        lines = []
        lines.append(self._heading("Data Export", 1))

        if self.options.include_metadata:
            lines.append(f"*Exported at: {datetime.utcnow().isoformat()}*\n")
            lines.append(f"*Records: {len(data)}*\n\n")

        # Determine columns
        if self.columns:
            headers = [col.header or col.field for col in self.columns if col.include]
            fields = [col.field for col in self.columns if col.include]
        else:
            fields = list(data[0].keys())
            headers = fields

        # Build table rows
        rows = []
        for item in data:
            row = []
            for field in fields:
                value = item.get(field, "")
                if isinstance(value, datetime):
                    value = self._format_datetime(value)
                elif isinstance(value, (list, dict)):
                    import json

                    value = json.dumps(value)
                row.append(str(value) if value is not None else "")
            rows.append(row)

        lines.append(self._table(headers, rows))

        return "".join(lines)
