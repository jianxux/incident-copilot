"""CSV export formatter with configurable columns."""

import csv
import io
from datetime import datetime
from typing import Any

from ..models import (
    ColumnConfig,
    CSVOptions,
    ExportType,
    RelatedDataConfig,
)


class CSVFormatter:
    """Formatter for CSV exports."""

    def __init__(
        self,
        export_type: ExportType,
        columns: list[ColumnConfig] | None = None,
        options: CSVOptions | None = None,
        related_data: RelatedDataConfig | None = None,
    ):
        self.export_type = export_type
        self.columns = columns or []
        self.options = options or CSVOptions()
        self.related_data = related_data or RelatedDataConfig()

    def format(self, data: list[dict[str, Any]]) -> str:
        """Format data as CSV string."""
        if not data:
            return ""

        output = io.StringIO()

        # Determine columns from config or data
        if self.columns:
            fieldnames = [col.field for col in self.columns if col.include]
            headers = {
                col.field: col.header or col.field
                for col in self.columns
                if col.include
            }
        else:
            fieldnames = list(data[0].keys()) if data else []
            headers = {f: f for f in fieldnames}

        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
            delimiter=self.options.delimiter,
            quotechar=self.options.quote_char,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator=self.options.line_ending,
        )

        # Write header with custom names
        if self.options.include_header:
            writer.writerow({f: headers.get(f, f) for f in fieldnames})

        # Write data rows
        for row in data:
            formatted_row = self._format_row(row, fieldnames)
            writer.writerow(formatted_row)

        return output.getvalue()

    def format_bytes(self, data: list[dict[str, Any]]) -> bytes:
        """Format data as CSV bytes."""
        csv_string = self.format(data)
        return csv_string.encode(self.options.encoding)

    def _format_row(self, row: dict[str, Any], fieldnames: list[str]) -> dict[str, str]:
        """Format a single row with proper value handling."""
        formatted = {}

        column_formats = {col.field: col.format for col in self.columns}

        for field in fieldnames:
            value = row.get(field)
            col_format = column_formats.get(field)
            formatted[field] = self._format_value(value, col_format)

        return formatted

    def _format_value(self, value: Any, format_type: str | None = None) -> str:
        """Format a single value for CSV output."""
        if value is None:
            return ""

        if isinstance(value, datetime):
            if format_type == "date":
                return value.strftime("%Y-%m-%d")
            elif format_type == "time":
                return value.strftime("%H:%M:%S")
            return value.isoformat()

        if isinstance(value, bool):
            return "Yes" if value else "No"

        if isinstance(value, (list, dict)):
            import json

            return json.dumps(value)

        if isinstance(value, float):
            if format_type == "percentage":
                return f"{value * 100:.2f}%"
            elif format_type == "currency":
                return f"${value:,.2f}"
            return str(value)

        str_value = str(value)

        # Escape formulas to prevent CSV injection
        if self.options.escape_formulas:
            if str_value.startswith(("=", "+", "-", "@", "\t", "\r")):
                str_value = "'" + str_value

        return str_value

    def format_incidents(self, incidents: list[dict[str, Any]]) -> str:
        """Format incident data as CSV."""
        flattened = []
        for incident in incidents:
            flat = self._flatten_incident(incident)
            flattened.append(flat)
        return self.format(flattened)

    def format_postmortems(self, postmortems: list[dict[str, Any]]) -> str:
        """Format postmortem data as CSV."""
        flattened = []
        for pm in postmortems:
            flat = self._flatten_postmortem(pm)
            flattened.append(flat)
        return self.format(flattened)

    def format_analytics(self, analytics: dict[str, Any]) -> str:
        """Format analytics data as CSV."""
        rows = self._flatten_analytics(analytics)
        return self.format(rows)

    def _flatten_incident(self, incident: dict[str, Any]) -> dict[str, Any]:
        """Flatten incident for CSV export."""
        flat = {
            "incident_id": incident.get("incident_id"),
            "title": incident.get("title"),
            "severity": incident.get("severity"),
            "service_name": incident.get("service_name"),
            "status": incident.get("status", "unknown"),
            "triggered_at": incident.get("triggered_at"),
            "resolved_at": incident.get("resolved_at"),
            "alert_url": incident.get("alert_url"),
        }

        # Calculate duration if resolved
        if flat.get("triggered_at") and flat.get("resolved_at"):
            triggered = flat["triggered_at"]
            resolved = flat["resolved_at"]
            if isinstance(triggered, str):
                triggered = datetime.fromisoformat(triggered.replace("Z", "+00:00"))
            if isinstance(resolved, str):
                resolved = datetime.fromisoformat(resolved.replace("Z", "+00:00"))
            if isinstance(triggered, datetime) and isinstance(resolved, datetime):
                duration = (resolved - triggered).total_seconds() / 60
                flat["duration_minutes"] = round(duration, 1)

        # Flatten nested data if included
        if self.related_data.include_timeline:
            timeline = incident.get("timeline", [])
            flat["timeline_events_count"] = len(timeline)
            if timeline:
                flat["first_event"] = timeline[0].get("title", "") if timeline else ""
                flat["last_event"] = timeline[-1].get("title", "") if timeline else ""

        if self.related_data.include_action_items:
            actions = incident.get("action_items", [])
            flat["action_items_count"] = len(actions)
            flat["action_items_open"] = sum(
                1 for a in actions if a.get("status") != "done"
            )

        return flat

    def _flatten_postmortem(self, pm: dict[str, Any]) -> dict[str, Any]:
        """Flatten postmortem for CSV export."""
        flat = {
            "id": pm.get("id"),
            "incident_id": pm.get("incident_id"),
            "title": pm.get("title"),
            "service_name": pm.get("service_name"),
            "severity": pm.get("severity"),
            "status": pm.get("status"),
            "created_at": pm.get("created_at"),
            "created_by": pm.get("created_by"),
            "incident_started_at": pm.get("incident_started_at"),
            "incident_resolved_at": pm.get("incident_resolved_at"),
            "incident_duration_minutes": pm.get("incident_duration_minutes"),
        }

        if self.related_data.include_root_cause:
            root_cause = pm.get("root_cause", {})
            if root_cause:
                flat["primary_cause"] = root_cause.get("primary_cause")
                flat["trigger"] = root_cause.get("trigger")
                flat["contributing_factors"] = ", ".join(
                    root_cause.get("contributing_factors", [])
                )

        if self.related_data.include_impact:
            impact = pm.get("impact", {})
            if impact:
                flat["users_affected"] = impact.get("users_affected")
                flat["sla_breach"] = impact.get("sla_breach")
                flat["services_affected"] = ", ".join(
                    impact.get("services_affected", [])
                )

        if self.related_data.include_action_items:
            actions = pm.get("action_items", [])
            flat["action_items_count"] = len(actions)
            flat["action_items_done"] = sum(
                1 for a in actions if a.get("status") == "done"
            )

        return flat

    def _flatten_analytics(self, analytics: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten analytics data into rows."""
        rows = []

        # MTTR stats
        if "mttr_stats" in analytics:
            stats = analytics["mttr_stats"]
            rows.append(
                {
                    "metric_name": "Mean MTTR",
                    "value": stats.get("mean_mttr_minutes"),
                    "unit": "minutes",
                    "period": stats.get("period"),
                }
            )
            rows.append(
                {
                    "metric_name": "Median MTTR",
                    "value": stats.get("median_mttr_minutes"),
                    "unit": "minutes",
                    "period": stats.get("period"),
                }
            )
            rows.append(
                {
                    "metric_name": "P90 MTTR",
                    "value": stats.get("p90_mttr_minutes"),
                    "unit": "minutes",
                    "period": stats.get("period"),
                }
            )
            rows.append(
                {
                    "metric_name": "Incidents Count",
                    "value": stats.get("incidents_count"),
                    "unit": "count",
                    "period": stats.get("period"),
                }
            )

        # Severity breakdown
        if "severity_breakdown" in analytics:
            for severity, count in analytics["severity_breakdown"].items():
                rows.append(
                    {
                        "metric_name": f"Incidents - {severity}",
                        "value": count,
                        "unit": "count",
                        "period": analytics.get("period"),
                    }
                )

        # Service breakdown
        if "service_breakdown" in analytics:
            for service, count in analytics["service_breakdown"].items():
                rows.append(
                    {
                        "metric_name": f"Service Incidents - {service}",
                        "value": count,
                        "unit": "count",
                        "period": analytics.get("period"),
                    }
                )

        return rows
