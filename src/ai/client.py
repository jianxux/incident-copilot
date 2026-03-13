"""AI Service Client - calls external AI service or falls back to stubs."""

from __future__ import annotations

import os

import httpx
import structlog

logger = structlog.get_logger()

AI_SERVICE_URL = os.environ.get("AI_SERVICE_URL", "")
AI_SERVICE_SECRET = os.environ.get("AI_SERVICE_SECRET", "")


class AIServiceClient:
    """Client for the proprietary AI service.

    Falls back to basic responses when the service is not configured.
    """

    def __init__(self) -> None:
        self.base_url = AI_SERVICE_URL.rstrip("/") if AI_SERVICE_URL else ""
        self.enabled = bool(self.base_url)
        headers = {}
        if AI_SERVICE_SECRET:
            headers["Authorization"] = f"Bearer {AI_SERVICE_SECRET}"
        self._client: httpx.AsyncClient | None = (
            httpx.AsyncClient(timeout=30.0, headers=headers) if self.enabled else None
        )
        if self.enabled:
            logger.info("ai_service_client_enabled", url=self.base_url)
        else:
            logger.info(
                "ai_service_client_disabled", hint="Set AI_SERVICE_URL to enable"
            )

    async def _post(self, path: str, payload: dict) -> dict:
        assert self._client is not None
        resp = await self._client.post(f"{self.base_url}{path}", json=payload)
        resp.raise_for_status()
        return resp.json()

    # ── Summarize ──────────────────────────────────────────────

    async def summarize_logs(
        self,
        logs: list[dict],
        similar_incidents: list[dict] | None = None,
    ) -> dict:
        if self.enabled:
            return await self._post(
                "/api/v1/summarize",
                {"logs": logs, "similar_incidents": similar_incidents or []},
            )
        return self._stub_summary(logs)

    # ── Verdict ────────────────────────────────────────────────

    async def generate_verdict(
        self,
        alert_data: dict,
        deploys: list,
        log_summary: str,
        metrics: dict | None = None,
        similar_incidents: list | None = None,
    ) -> dict:
        if self.enabled:
            return await self._post(
                "/api/v1/verdict",
                {
                    "alert": alert_data,
                    "deploys": deploys,
                    "log_summary": log_summary,
                    "metrics": metrics,
                    "similar_incidents": similar_incidents or [],
                },
            )
        return self._stub_verdict(alert_data)

    # ── Log compression ────────────────────────────────────────

    async def compress_logs(self, logs: list[dict], max_tokens: int = 4000) -> dict:
        if self.enabled:
            return await self._post(
                "/api/v1/compress-logs",
                {"logs": logs, "max_tokens": max_tokens},
            )
        return self._stub_compress(logs)

    # ── Copilot chat ───────────────────────────────────────────

    async def chat(
        self, session_id: str, message: str, context: dict | None = None
    ) -> dict:
        if self.enabled:
            return await self._post(
                "/api/v1/chat",
                {"session_id": session_id, "message": message, "context": context},
            )
        return {
            "response": (
                "AI copilot is not configured. "
                "Set AI_SERVICE_URL to enable intelligent assistance."
            ),
            "role": "assistant",
        }

    async def generate_summary(self, session_id: str, context: dict) -> str:
        if self.enabled:
            data = await self._post(
                "/api/v1/summary",
                {"session_id": session_id, "context": context},
            )
            return data.get("summary", "")
        return "AI summary not available. Configure AI_SERVICE_URL for intelligent summaries."

    async def suggest_next_steps(self, context: dict) -> list[str]:
        if self.enabled:
            data = await self._post("/api/v1/next-steps", {"context": context})
            return data.get("steps", [])
        return [
            "Check recent deployments",
            "Review error logs",
            "Check service dependencies",
        ]

    # ── Digest ─────────────────────────────────────────────────

    async def generate_digest(
        self, incidents: list[dict], period: str = "daily"
    ) -> dict:
        if self.enabled:
            return await self._post(
                "/api/v1/digest",
                {"incidents": incidents, "period": period},
            )
        return {
            "summary": "AI digest not available.",
            "insights": [],
            "recommendations": [],
        }

    # ── Stubs ──────────────────────────────────────────────────

    @staticmethod
    def _stub_summary(logs: list[dict]) -> dict:
        error_count = sum(
            1
            for log in logs
            if log.get("level") in ("error", "ERROR", "critical", "CRITICAL")
        )
        return {
            "summary": (
                f"Found {len(logs)} log entries ({error_count} errors). "
                "Configure AI_SERVICE_URL for intelligent analysis."
            ),
            "key_errors": [],
            "patterns": [],
        }

    @staticmethod
    def _stub_verdict(alert_data: dict) -> dict:
        return {
            "verdict": (
                f"Alert received: {alert_data.get('title', 'Unknown')}. "
                "Configure AI_SERVICE_URL for root cause analysis."
            ),
            "confidence": 0,
            "suggested_actions": ["Check recent deployments", "Review error logs"],
            "root_cause": "AI analysis not available",
        }

    @staticmethod
    def _stub_compress(logs: list[dict]) -> dict:
        return {
            "compressed": logs[:50],
            "total": len(logs),
            "kept": min(len(logs), 50),
        }


# Global singleton
ai_client = AIServiceClient()
