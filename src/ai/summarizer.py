"""AI-powered log summarization."""

import json

import structlog
from anthropic import AsyncAnthropic

from ..config import Settings
from ..models import AILogSummary, LogEntry

logger = structlog.get_logger()

SUMMARIZE_PROMPT = """You are an expert SRE analyzing error logs during an incident. Given the following log entries, provide a concise analysis.

Service: {service_name}
Time range: Last {time_range} minutes
Number of log entries: {log_count}

Log entries (most recent first):
{logs}

Analyze these logs and respond with a JSON object containing:
- "top_issues": array of 3-5 short descriptions of the main error patterns (most frequent/severe first)
- "explanation": a 1-2 sentence plain English explanation of what's happening
- "likely_cause": your best guess at the root cause (or null if unclear)
- "suggested_actions": array of 2-3 concrete next steps to investigate/resolve

Be concise and actionable. Focus on patterns, not individual log lines.

Respond ONLY with the JSON object, no other text."""


class LogSummarizer:
    """AI-powered log summarizer using Claude."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
        self.model = settings.ai_model

    async def summarize(
        self, logs: list[LogEntry], service_name: str, time_range_minutes: int = 15
    ) -> AILogSummary | None:
        """Summarize logs using Claude."""
        if not self.client:
            logger.warning("anthropic_not_configured")
            return None

        if not logs:
            return AILogSummary(
                top_issues=["No error logs found in the time range"],
                explanation="No errors or warnings were logged in the specified time range.",
            )

        try:
            # Format logs for the prompt
            log_text = self._format_logs(logs)

            prompt = SUMMARIZE_PROMPT.format(
                service_name=service_name,
                time_range=time_range_minutes,
                log_count=len(logs),
                logs=log_text,
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse JSON response
            content = response.content[0].text
            data = json.loads(content)

            return AILogSummary(
                top_issues=data.get("top_issues", []),
                explanation=data.get("explanation", ""),
                likely_cause=data.get("likely_cause"),
                suggested_actions=data.get("suggested_actions", []),
            )

        except json.JSONDecodeError as e:
            logger.error("ai_response_not_json", error=str(e))
            return None
        except Exception as e:
            logger.error("ai_summarization_failed", error=str(e))
            return None

    def _format_logs(self, logs: list[LogEntry], max_logs: int = 50) -> str:
        """Format logs for the prompt, limiting total size."""
        lines = []

        for log in logs[:max_logs]:
            timestamp = log.timestamp.strftime("%H:%M:%S")
            level = log.level.upper()[:5]
            message = log.message[:300]  # Truncate long messages
            lines.append(f"[{timestamp}] {level} | {message}")

        return "\n".join(lines)
