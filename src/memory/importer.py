"""Cold start importer for incident memory bootstrap."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any

import structlog

from .capture import IncidentCapture

logger = structlog.get_logger()


@dataclass
class ImportResult:
    """Incident import operation summary."""

    imported_count: int
    failed_count: int
    failed_items: list[dict[str, object]]


class IncidentMemoryImporter:
    """Import incidents from JSON/CSV payloads into memory storage."""

    def __init__(self, capture: IncidentCapture):
        self.capture = capture

    async def import_content(
        self,
        filename: str,
        content: bytes,
        format_hint: str | None = None,
    ) -> ImportResult:
        incidents = self._parse_incidents(
            filename=filename, content=content, format_hint=format_hint
        )

        imported_count = 0
        failed_items: list[dict[str, object]] = []

        for index, incident in enumerate(incidents):
            try:
                record = await self.capture.capture(incident)
                imported_count += 1
                logger.info(
                    "incident_memory_imported_record",
                    incident_id=record.id,
                    filename=filename,
                )
            except Exception as exc:
                failed_items.append(
                    {
                        "index": index,
                        "incident_id": str(
                            incident.get("id") or incident.get("incident_id") or ""
                        ),
                        "error": str(exc),
                    }
                )
                logger.error(
                    "incident_memory_import_failed",
                    filename=filename,
                    index=index,
                    error=str(exc),
                )

        return ImportResult(
            imported_count=imported_count,
            failed_count=len(failed_items),
            failed_items=failed_items,
        )

    def _parse_incidents(
        self,
        filename: str,
        content: bytes,
        format_hint: str | None,
    ) -> list[dict[str, Any]]:
        payload = content.decode("utf-8")
        fmt = (format_hint or self._infer_format(filename)).lower()

        if fmt == "json":
            data = json.loads(payload)
            if isinstance(data, list):
                return [self._ensure_dict(item) for item in data]
            if isinstance(data, dict):
                incidents = data.get("incidents")
                if isinstance(incidents, list):
                    return [self._ensure_dict(item) for item in incidents]
                return [self._ensure_dict(data)]
            raise ValueError("JSON import payload must be an object or array")

        if fmt == "csv":
            reader = csv.DictReader(io.StringIO(payload))
            return [dict(row) for row in reader]

        raise ValueError("Unsupported import format. Use CSV or JSON.")

    @staticmethod
    def _infer_format(filename: str) -> str:
        lowered = filename.lower()
        if lowered.endswith(".json"):
            return "json"
        if lowered.endswith(".csv"):
            return "csv"
        raise ValueError("Could not infer format from filename. Provide format_hint.")

    @staticmethod
    def _ensure_dict(value: object) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        raise ValueError("Each incident must be a JSON object")
