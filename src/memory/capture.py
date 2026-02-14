"""Incident memory capture pipeline."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import httpx
import structlog
from anthropic import AsyncAnthropic

from ..config import Settings
from .config import IncidentMemoryConfig
from .models import IncidentRecord
from .store import IncidentMemoryStore

logger = structlog.get_logger()

CAPTURE_PROMPT = """You are an SRE incident analyst.
Extract structured incident memory fields from the incident narrative.
Return ONLY valid JSON matching this schema:
{{
  "title": "string",
  "created_at": "ISO-8601 datetime",
  "resolved_at": "ISO-8601 datetime or null",
  "duration_minutes": "integer or null",
  "severity": "critical|high|medium|low|info|unknown",
  "services_affected": ["string"],
  "root_cause_category": "string or null",
  "root_cause_summary": "string or null",
  "error_signatures": ["string"],
  "metric_anomalies": ["string"],
  "deploy_involved": "boolean",
  "deploy_sha": "string or null",
  "resolution_steps": ["string"],
  "resolution_summary": "string or null",
  "time_to_diagnose_minutes": "integer or null",
  "time_to_fix_minutes": "integer or null",
  "was_rollback": "boolean or null",
  "runbook_used": "string or null",
  "what_helped": "string or null",
  "what_was_missing": "string or null",
  "tags": ["string"]
}}

Rules:
- Use null when unknown.
- Keep summaries concise and factual.
- Do not include extra keys.

Incident payload:
{incident_payload}
"""


class IncidentCapture:
    """Extract, embed, and persist incident memory records."""

    def __init__(
        self,
        settings: Settings,
        store: IncidentMemoryStore,
        config: IncidentMemoryConfig | None = None,
        anthropic_client: AsyncAnthropic | None = None,
    ):
        self.settings = settings
        self.config = config or IncidentMemoryConfig.from_settings(settings)
        self.store = store
        self.model = self.config.capture_model
        self._anthropic_client = anthropic_client or (
            AsyncAnthropic(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )
        self._embed_client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        """Close network clients."""
        if self._embed_client and not self._embed_client.is_closed:
            await self._embed_client.aclose()
            self._embed_client = None

    async def capture(self, raw_incident: dict[str, Any]) -> IncidentRecord:
        """Capture a raw incident payload into a structured memory record."""
        extracted = await self._extract_structured(raw_incident)

        incident_id = str(
            raw_incident.get("id")
            or raw_incident.get("incident_id")
            or extracted.get("id")
            or f"im-{uuid.uuid4().hex[:12]}"
        )

        narrative = self._build_narrative(raw_incident, extracted)
        embedding = await self._embed_text(narrative)

        record = IncidentRecord(
            id=incident_id,
            title=str(
                extracted.get("title")
                or raw_incident.get("title")
                or "Untitled incident"
            ),
            created_at=self._parse_datetime(
                extracted.get("created_at")
                or raw_incident.get("created_at")
                or raw_incident.get("triggered_at")
            )
            or datetime.utcnow(),
            resolved_at=self._parse_datetime(
                extracted.get("resolved_at") or raw_incident.get("resolved_at")
            ),
            duration_minutes=self._safe_int(extracted.get("duration_minutes")),
            severity=self._normalize_str(extracted.get("severity")),
            services_affected=self._safe_list(extracted.get("services_affected")),
            root_cause_category=self._normalize_str(
                extracted.get("root_cause_category")
            ),
            root_cause_summary=self._normalize_str(extracted.get("root_cause_summary")),
            error_signatures=self._safe_list(extracted.get("error_signatures")),
            metric_anomalies=self._safe_list(extracted.get("metric_anomalies")),
            deploy_involved=bool(extracted.get("deploy_involved", False)),
            deploy_sha=self._normalize_str(extracted.get("deploy_sha")),
            resolution_steps=self._safe_list(extracted.get("resolution_steps")),
            resolution_summary=self._normalize_str(extracted.get("resolution_summary")),
            time_to_diagnose_minutes=self._safe_int(
                extracted.get("time_to_diagnose_minutes")
            ),
            time_to_fix_minutes=self._safe_int(extracted.get("time_to_fix_minutes")),
            was_rollback=self._safe_bool(extracted.get("was_rollback")),
            runbook_used=self._normalize_str(extracted.get("runbook_used")),
            what_helped=self._normalize_str(extracted.get("what_helped")),
            what_was_missing=self._normalize_str(extracted.get("what_was_missing")),
            tags=self._safe_list(extracted.get("tags")),
            embedding=embedding,
        )

        await self.store.store(record)
        logger.info("incident_memory_captured", incident_id=record.id)
        return record

    async def _extract_structured(self, raw_incident: dict[str, Any]) -> dict[str, Any]:
        if not self._anthropic_client:
            logger.warning(
                "incident_capture_no_claude", reason="anthropic_not_configured"
            )
            return raw_incident

        prompt = CAPTURE_PROMPT.format(
            incident_payload=json.dumps(raw_incident, default=str)
        )

        try:
            response = await self._anthropic_client.messages.create(
                model=self.model,
                max_tokens=self.config.capture_max_tokens,
                temperature=self.config.capture_temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(getattr(block, "text", "") for block in response.content)
            return self._parse_json(text)
        except Exception as exc:
            logger.error("incident_capture_extract_failed", error=str(exc))
            return raw_incident

    async def _embed_text(self, text: str) -> list[float]:
        if not self.settings.openai_api_key:
            logger.warning("incident_capture_no_openai", reason="openai_not_configured")
            return [0.0] * self.config.embedding_dimensions

        client = await self._get_embed_client()

        response = await client.post(
            "/embeddings",
            json={
                "model": self.config.embedding_model,
                "input": text,
            },
        )
        response.raise_for_status()
        payload = response.json()
        embedding = payload["data"][0]["embedding"]
        return [float(value) for value in embedding]

    async def _get_embed_client(self) -> httpx.AsyncClient:
        if self._embed_client is None or self._embed_client.is_closed:
            self._embed_client = httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._embed_client

    @staticmethod
    def _build_narrative(
        raw_incident: dict[str, Any], extracted: dict[str, Any]
    ) -> str:
        lines = []
        for key in (
            "title",
            "description",
            "summary",
            "root_cause_summary",
            "resolution_summary",
            "what_helped",
            "what_was_missing",
        ):
            value = extracted.get(key) or raw_incident.get(key)
            if value:
                lines.append(f"{key}: {value}")

        for key in (
            "services_affected",
            "error_signatures",
            "metric_anomalies",
            "tags",
        ):
            value = extracted.get(key)
            if isinstance(value, list) and value:
                lines.append(f"{key}: {', '.join(str(v) for v in value)}")

        return "\n".join(lines)[:8000]

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        return json.loads(text.strip())

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            candidate = value.strip().replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                return None
        return None

    @staticmethod
    def _safe_int(value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_bool(value: object) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0"}:
                return False
        return None

    @staticmethod
    def _safe_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return []

    @staticmethod
    def _normalize_str(value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None
