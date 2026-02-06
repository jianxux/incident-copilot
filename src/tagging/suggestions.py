"""AI-powered tag suggestions for incidents."""

import json

import structlog
from anthropic import AsyncAnthropic

from ..config import Settings
from .models import Tag, TagSuggestion

logger = structlog.get_logger()

SUGGESTION_PROMPT = """You are an expert SRE helping to categorize incidents. Suggest relevant tags.

Incident:
- Title: {title}
- Service: {service_name}
- Severity: {severity}
- Description: {description}

Available Tags:
{available_tags}

Respond with a JSON array of suggestions with tag_id, tag_name, confidence (0-1), and reason.
Respond ONLY with the JSON array."""


class TagSuggester:
    """AI-powered tag suggestion service."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            AsyncAnthropic(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )
        self.model = settings.ai_model

    async def suggest_tags(
        self,
        title: str,
        service_name: str,
        severity: str,
        description: str | None,
        available_tags: list[Tag],
        max_suggestions: int = 5,
        min_confidence: float = 0.5,
    ) -> list[TagSuggestion]:
        """Suggest relevant tags for an incident using AI."""
        if not self.client:
            return self._fallback_suggestions(
                service_name, severity, available_tags, max_suggestions
            )
        if not available_tags:
            return []
        try:
            tags_text = "\n".join(f"- {t.id}: {t.name}" for t in available_tags)
            prompt = SUGGESTION_PROMPT.format(
                title=title,
                service_name=service_name,
                severity=severity,
                description=description or "No description",
                available_tags=tags_text,
            )
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text
            suggestions_data = json.loads(content)
            suggestions = []
            tag_id_map = {t.id: t for t in available_tags}
            for item in suggestions_data:
                tag_id = item.get("tag_id")
                if tag_id not in tag_id_map:
                    continue
                confidence = float(item.get("confidence", 0))
                if confidence < min_confidence:
                    continue
                suggestions.append(
                    TagSuggestion(
                        tag_id=tag_id,
                        tag_name=item.get("tag_name", tag_id_map[tag_id].name),
                        confidence=min(1.0, max(0.0, confidence)),
                        reason=item.get("reason", "AI suggested"),
                    )
                )
            suggestions.sort(key=lambda s: s.confidence, reverse=True)
            return suggestions[:max_suggestions]
        except (json.JSONDecodeError, Exception) as e:
            logger.error("ai_suggestion_failed", error=str(e))
            return self._fallback_suggestions(
                service_name, severity, available_tags, max_suggestions
            )

    def _fallback_suggestions(
        self,
        service_name: str,
        severity: str,
        available_tags: list[Tag],
        max_suggestions: int,
    ) -> list[TagSuggestion]:
        """Fallback tag suggestions using simple matching."""
        suggestions = []
        service_lower = service_name.lower()
        severity_lower = severity.lower()
        for tag in available_tags:
            tag_name_lower = tag.name.lower()
            confidence = 0.0
            reason = ""
            if tag_name_lower in service_lower or service_lower in tag_name_lower:
                confidence = 0.8
                reason = f"Tag name matches service '{service_name}'"
            elif tag_name_lower == severity_lower:
                confidence = 0.7
                reason = f"Tag matches severity level '{severity}'"
            if confidence > 0:
                suggestions.append(
                    TagSuggestion(
                        tag_id=tag.id,
                        tag_name=tag.name,
                        confidence=confidence,
                        reason=reason,
                    )
                )
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions[:max_suggestions]


_suggester: TagSuggester | None = None


def get_tag_suggester(settings: Settings | None = None) -> TagSuggester:
    """Get or create the tag suggester instance."""
    global _suggester
    if _suggester is None:
        if settings is None:
            from ..config import get_settings

            settings = get_settings()
        _suggester = TagSuggester(settings)
    return _suggester
