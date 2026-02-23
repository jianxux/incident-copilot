"""Incident memory recall pipeline."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import httpx
import structlog
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from ..config import Settings
from .config import IncidentMemoryConfig
from .feedback import FeedbackStore, get_feedback_store
from .models import IncidentRecallResult
from .scoring import apply_feedback_weight, apply_temporal_decay
from .store import IncidentMemoryStore

logger = structlog.get_logger()

RERANK_PROMPT = """You are helping incident response.
Given the current alert context and candidate past incidents, reorder candidates by practical usefulness.
Prioritize: same symptoms, same services, successful fast resolution, and high confidence root cause.

Current alert:
{query_context}

Candidates:
{candidates_json}

Respond ONLY JSON:
{{
  "ranked_ids": ["id1", "id2", "id3"]
}}
"""


class RecallQuery(BaseModel):
    """Query parameters for memory recall."""

    narrative: str = Field(..., min_length=1)
    services: list[str] = Field(default_factory=list)
    severity: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    lookback_days: int | None = None
    limit: int = Field(default=5, ge=1, le=50)
    candidate_limit: int | None = Field(default=None, ge=1, le=200)
    min_similarity: float | None = Field(default=None, ge=-1.0, le=1.0)
    rerank_with_claude: bool | None = None
    incident_id: str | None = None

    # Filled by recall service before store call
    embedding: list[float] = Field(default_factory=list)


class IncidentRecall:
    """Retrieve relevant incident memory records for a live incident."""

    def __init__(
        self,
        settings: Settings,
        store: IncidentMemoryStore,
        config: IncidentMemoryConfig | None = None,
        anthropic_client: AsyncAnthropic | None = None,
        feedback_store: FeedbackStore | None = None,
    ):
        self.settings = settings
        self.config = config or IncidentMemoryConfig.from_settings(settings)
        self.store = store
        self._anthropic_client = anthropic_client or (
            AsyncAnthropic(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )
        self.feedback_store = feedback_store or get_feedback_store(
            database_path=self.config.feedback_database_path
        )
        self._embed_client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        """Close network clients."""
        if self._embed_client and not self._embed_client.is_closed:
            await self._embed_client.aclose()
            self._embed_client = None

    async def recall(self, query: RecallQuery) -> list[IncidentRecallResult]:
        """Recall similar incidents from memory store."""
        query.embedding = await self._embed_text(query.narrative)

        if query.lookback_days is not None and query.start_time is None:
            query.start_time = datetime.utcnow() - timedelta(days=query.lookback_days)

        matches = await self.store.recall(query)
        matches = await self._apply_temporal_decay_and_feedback(matches, query)

        if self._should_rerank(query):
            reranked = await self._rerank(query, matches)
            if reranked is not None:
                return reranked

        return matches

    async def _apply_temporal_decay_and_feedback(
        self,
        matches: list[IncidentRecallResult],
        query: RecallQuery,
    ) -> list[IncidentRecallResult]:
        """Recompute temporal decay and apply feedback-based score refinement."""
        if not matches:
            return matches

        feedback_summaries = await self._load_feedback_summaries(matches)
        now = datetime.utcnow()
        refined: list[IncidentRecallResult] = []

        for item in matches:
            created_at = item.record.created_at
            days_ago = 0
            try:
                delta = now - created_at.replace(tzinfo=None)
                days_ago = max(int(delta.total_seconds() // 86400), 0)
            except Exception:
                days_ago = 0

            decayed_similarity = apply_temporal_decay(
                similarity=item.vector_similarity,
                days_ago=days_ago,
                decay_rate=self.config.recall_temporal_decay_rate,
                window_days=self.config.recall_temporal_decay_window_days,
            )

            structured_boost = item.score - (
                item.vector_similarity * max(item.temporal_decay, 0.0)
            )

            new_decay = (
                decayed_similarity / item.vector_similarity
                if item.vector_similarity > 0
                else 0.0
            )
            item.temporal_decay = round(new_decay, 6)
            base_score = max(decayed_similarity + structured_boost, 0.0)
            item.score = apply_feedback_weight(
                score=base_score,
                feedback_summary=feedback_summaries.get(item.record.id),
            )
            refined.append(item)

        refined.sort(key=lambda result: result.score, reverse=True)
        return refined

    async def _load_feedback_summaries(
        self,
        matches: list[IncidentRecallResult],
    ) -> dict[str, dict[str, int | float]]:
        incident_ids = list({item.record.id for item in matches})
        summaries = await asyncio.gather(
            *(
                self.feedback_store.get_feedback_summary(recalled_incident_id)
                for recalled_incident_id in incident_ids
            )
        )
        return {
            incident_id: summary
            for incident_id, summary in zip(incident_ids, summaries, strict=True)
        }

    async def _embed_text(self, text: str) -> list[float]:
        if not self.settings.openai_api_key:
            logger.warning("incident_recall_no_openai", reason="openai_not_configured")
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
        return [float(value) for value in payload["data"][0]["embedding"]]

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

    def _should_rerank(self, query: RecallQuery) -> bool:
        if query.rerank_with_claude is not None:
            return query.rerank_with_claude and self._anthropic_client is not None

        if not self.config.recall_enable_rerank or self._anthropic_client is None:
            return False

        severity_order = {
            "info": 0,
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4,
        }
        threshold = severity_order.get(
            self.config.recall_rerank_severity_threshold.lower(),
            3,
        )
        current = severity_order.get((query.severity or "").lower(), -1)
        return current >= threshold

    async def _rerank(
        self,
        query: RecallQuery,
        matches: list[IncidentRecallResult],
    ) -> list[IncidentRecallResult] | None:
        if not matches:
            return matches

        assert self._anthropic_client is not None

        candidates = [
            {
                "id": item.record.id,
                "title": item.record.title,
                "severity": item.record.severity,
                "services": item.record.services_affected,
                "root_cause_summary": item.record.root_cause_summary,
                "resolution_summary": item.record.resolution_summary,
                "score": item.score,
            }
            for item in matches
        ]
        query_context = {
            "severity": query.severity,
            "services": query.services,
            "narrative": query.narrative[:4000],
        }

        prompt = RERANK_PROMPT.format(
            query_context=json.dumps(query_context),
            candidates_json=json.dumps(candidates),
        )

        try:
            response = await self._anthropic_client.messages.create(
                model=self.config.recall_rerank_model,
                max_tokens=self.config.recall_rerank_max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            content = "".join(getattr(block, "text", "") for block in response.content)
            data = self._parse_json(content)
            ranked_ids = data.get("ranked_ids", [])
            return self._reorder_matches(matches, ranked_ids)
        except Exception as exc:
            logger.error("incident_recall_rerank_failed", error=str(exc))
            return None

    @staticmethod
    def _reorder_matches(
        matches: list[IncidentRecallResult], ranked_ids: list[str]
    ) -> list[IncidentRecallResult]:
        by_id = {item.record.id: item for item in matches}
        ordered = [by_id[item_id] for item_id in ranked_ids if item_id in by_id]
        seen = {item.record.id for item in ordered}
        ordered.extend(item for item in matches if item.record.id not in seen)
        return ordered

    @staticmethod
    def _parse_json(content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        return json.loads(text.strip())
