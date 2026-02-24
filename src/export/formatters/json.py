"""JSON export formatter with schema options."""

import json
from datetime import datetime, UTC
from typing import Any

from ..models import (
    ColumnConfig,
    ExportType,
    JSONOptions,
    RelatedDataConfig,
)


class JSONFormatter:
    """Formatter for JSON exports."""

    SCHEMA_VERSION = "1.0"

    def __init__(
        self,
        export_type: ExportType,
        columns: list[ColumnConfig] | None = None,
        options: JSONOptions | None = None,
        related_data: RelatedDataConfig | None = None,
    ):
        self.export_type = export_type
        self.columns = columns or []
        self.options = options or JSONOptions()
        self.related_data = related_data or RelatedDataConfig()

    def format(self, data: list[dict[str, Any]] | dict[str, Any]) -> str:
        """Format data as JSON string."""
        output = self._prepare_output(data)

        return json.dumps(
            output,
            indent=self.options.indent,
            default=self._json_serializer,
            ensure_ascii=False,
        )

    def format_bytes(self, data: list[dict[str, Any]] | dict[str, Any]) -> bytes:
        """Format data as JSON bytes."""
        json_string = self.format(data)
        return json_string.encode("utf-8")

    def _prepare_output(
        self, data: list[dict[str, Any]] | dict[str, Any]
    ) -> dict[str, Any]:
        """Prepare output with optional schema and metadata."""
        # Filter columns if specified
        if isinstance(data, list):
            processed_data = [self._filter_fields(item) for item in data]
            if self.options.flatten:
                processed_data = [self._flatten_dict(item) for item in processed_data]
        else:
            processed_data = self._filter_fields(data)
            if self.options.flatten:
                processed_data = self._flatten_dict(processed_data)

        output: dict[str, Any] = {
            "data": processed_data,
            "metadata": {
                "export_type": self.export_type.value,
                "exported_at": datetime.now(UTC).isoformat(),
                "record_count": len(data) if isinstance(data, list) else 1,
            },
        }

        if self.options.include_schema:
            output["schema"] = self._generate_schema()

        return output

    def _filter_fields(self, item: dict[str, Any]) -> dict[str, Any]:
        """Filter fields based on column configuration."""
        if not self.columns:
            return item

        included_fields = {col.field for col in self.columns if col.include}
        return {k: v for k, v in item.items() if k in included_fields}

    def _flatten_dict(
        self, d: dict[str, Any], parent_key: str = "", sep: str = "_"
    ) -> dict[str, Any]:
        """Flatten a nested dictionary."""
        items: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep).items())
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                # Convert list of dicts to indexed keys
                for i, item in enumerate(v):
                    items.extend(
                        self._flatten_dict(item, f"{new_key}_{i}", sep).items()
                    )
            else:
                items.append((new_key, v))
        return dict(items)

    def _json_serializer(self, obj: Any) -> Any:
        """Custom JSON serializer for non-standard types."""
        if isinstance(obj, datetime):
            if self.options.date_format == "timestamp":
                return obj.timestamp()
            elif (
                self.options.date_format == "custom" and self.options.custom_date_format
            ):
                return obj.strftime(self.options.custom_date_format)
            return obj.isoformat()

        if hasattr(obj, "model_dump"):  # Pydantic v2
            return obj.model_dump()
        if hasattr(obj, "dict"):  # Pydantic v1
            return obj.dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__

        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def _generate_schema(self) -> dict[str, Any]:
        """Generate JSON schema for the export format."""
        schema: dict[str, Any] = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "version": self.options.schema_version,
            "type": "object",
            "properties": {
                "data": {"type": "array", "items": {}},
                "metadata": {
                    "type": "object",
                    "properties": {
                        "export_type": {"type": "string"},
                        "exported_at": {"type": "string", "format": "date-time"},
                        "record_count": {"type": "integer"},
                    },
                },
            },
        }

        # Add data item schema based on export type
        if self.export_type == ExportType.INCIDENTS:
            schema["properties"]["data"]["items"] = self._incident_schema()
        elif self.export_type == ExportType.POSTMORTEMS:
            schema["properties"]["data"]["items"] = self._postmortem_schema()
        elif self.export_type == ExportType.ANALYTICS:
            schema["properties"]["data"]["items"] = self._analytics_schema()

        return schema

    def _incident_schema(self) -> dict[str, Any]:
        """Schema for incident data."""
        return {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "title": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low", "info"],
                },
                "service_name": {"type": "string"},
                "status": {"type": "string"},
                "triggered_at": {"type": "string", "format": "date-time"},
                "resolved_at": {"type": ["string", "null"], "format": "date-time"},
                "alert_url": {"type": ["string", "null"]},
                "timeline": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "timestamp": {"type": "string", "format": "date-time"},
                            "event_type": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": ["string", "null"]},
                        },
                    },
                },
            },
            "required": ["incident_id", "title", "severity", "service_name"],
        }

    def _postmortem_schema(self) -> dict[str, Any]:
        """Schema for postmortem data."""
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "incident_id": {"type": "string"},
                "title": {"type": "string"},
                "service_name": {"type": "string"},
                "severity": {"type": "string"},
                "status": {"type": "string"},
                "executive_summary": {"type": "string"},
                "root_cause": {
                    "type": "object",
                    "properties": {
                        "primary_cause": {"type": "string"},
                        "contributing_factors": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "trigger": {"type": ["string", "null"]},
                    },
                },
                "impact": {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string"},
                        "users_affected": {"type": ["integer", "null"]},
                        "sla_breach": {"type": "boolean"},
                    },
                },
                "action_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "status": {"type": "string"},
                            "priority": {"type": "string"},
                            "owner": {"type": ["string", "null"]},
                        },
                    },
                },
            },
            "required": ["id", "incident_id", "title"],
        }

    def _analytics_schema(self) -> dict[str, Any]:
        """Schema for analytics data."""
        return {
            "type": "object",
            "properties": {
                "mttr_stats": {
                    "type": "object",
                    "properties": {
                        "period": {"type": "string"},
                        "mean_mttr_seconds": {"type": ["number", "null"]},
                        "median_mttr_seconds": {"type": ["number", "null"]},
                        "p90_mttr_seconds": {"type": ["number", "null"]},
                        "incidents_count": {"type": "integer"},
                    },
                },
                "severity_breakdown": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                },
                "service_breakdown": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                },
                "trends": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string", "format": "date"},
                            "incident_count": {"type": "integer"},
                            "mttr_minutes": {"type": ["number", "null"]},
                        },
                    },
                },
            },
        }

    def format_incidents(self, incidents: list[dict[str, Any]]) -> str:
        """Format incident data as JSON."""
        processed = []
        for incident in incidents:
            item = self._process_incident(incident)
            processed.append(item)
        return self.format(processed)

    def format_postmortems(self, postmortems: list[dict[str, Any]]) -> str:
        """Format postmortem data as JSON."""
        processed = []
        for pm in postmortems:
            item = self._process_postmortem(pm)
            processed.append(item)
        return self.format(processed)

    def format_analytics(self, analytics: dict[str, Any]) -> str:
        """Format analytics data as JSON."""
        return self.format(analytics)

    def _process_incident(self, incident: dict[str, Any]) -> dict[str, Any]:
        """Process incident data for JSON export."""
        result = dict(incident)

        # Handle timeline based on related_data config
        if not self.related_data.include_timeline:
            result.pop("timeline", None)
        elif self.related_data.max_timeline_events:
            if "timeline" in result:
                result["timeline"] = result["timeline"][
                    : self.related_data.max_timeline_events
                ]

        if not self.related_data.include_comments:
            result.pop("comments", None)
        elif self.related_data.max_comments:
            if "comments" in result:
                result["comments"] = result["comments"][
                    : self.related_data.max_comments
                ]

        if not self.related_data.include_attachments:
            result.pop("attachments", None)

        return result

    def _process_postmortem(self, pm: dict[str, Any]) -> dict[str, Any]:
        """Process postmortem data for JSON export."""
        result = dict(pm)

        if not self.related_data.include_timeline:
            result.pop("timeline", None)

        if not self.related_data.include_root_cause:
            result.pop("root_cause", None)

        if not self.related_data.include_impact:
            result.pop("impact", None)

        if not self.related_data.include_action_items:
            result.pop("action_items", None)

        return result
