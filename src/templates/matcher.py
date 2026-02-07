"""Template matching logic for auto-suggesting templates."""

import re
from dataclasses import dataclass

from .models import IncidentTemplate, MatchPattern, TemplateMatch


@dataclass
class AlertData:
    """Alert data for template matching."""

    title: str
    description: str | None = None
    service: str | None = None
    source: str | None = None
    tags: list[str] | None = None
    severity: str | None = None

    def get_field(self, field: str) -> str | None:
        """Get field value by name."""
        if field == "title":
            return self.title
        elif field == "description":
            return self.description
        elif field == "service":
            return self.service
        elif field == "source":
            return self.source
        elif field == "tags":
            return ",".join(self.tags) if self.tags else None
        elif field == "severity":
            return self.severity
        return None


class TemplateMatcher:
    """Matches alerts to templates based on patterns."""

    def __init__(self, templates: list[IncidentTemplate]):
        """Initialize with list of templates."""
        self.templates = [t for t in templates if t.is_active]

    def _match_pattern(self, pattern: MatchPattern, alert: AlertData) -> float:
        """Check if a pattern matches and return weighted score."""
        field_value = alert.get_field(pattern.field)
        if not field_value:
            return 0.0

        field_lower = field_value.lower()
        pattern_lower = pattern.value.lower()

        matched = False
        if pattern.operator == "contains":
            matched = pattern_lower in field_lower
        elif pattern.operator == "equals":
            matched = field_lower == pattern_lower
        elif pattern.operator == "starts_with":
            matched = field_lower.startswith(pattern_lower)
        elif pattern.operator == "regex":
            try:
                matched = bool(re.search(pattern.value, field_value, re.IGNORECASE))
            except re.error:
                matched = False

        return pattern.weight if matched else 0.0

    def _calculate_score(self, template: IncidentTemplate, alert: AlertData) -> tuple[float, list[str]]:
        """Calculate match score for a template against alert."""
        if not template.match_patterns:
            return 0.0, []

        total_score = 0.0
        max_possible = sum(p.weight for p in template.match_patterns)
        matched_patterns: list[str] = []

        for pattern in template.match_patterns:
            score = self._match_pattern(pattern, alert)
            if score > 0:
                total_score += score
                matched_patterns.append(f"{pattern.field}:{pattern.value}")

        # Normalize to 0-1 range
        normalized = total_score / max_possible if max_possible > 0 else 0.0
        return normalized, matched_patterns

    def match(self, alert: AlertData, limit: int = 5) -> list[TemplateMatch]:
        """Match alert to templates, return sorted by score."""
        matches: list[TemplateMatch] = []

        for template in self.templates:
            score, matched_patterns = self._calculate_score(template, alert)
            if score >= template.match_threshold:
                matches.append(TemplateMatch(
                    template_id=template.id,
                    template_name=template.name,
                    score=round(score, 3),
                    matched_patterns=matched_patterns,
                    category=template.category,
                ))

        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:limit]

    def best_match(self, alert: AlertData) -> TemplateMatch | None:
        """Get the best matching template."""
        matches = self.match(alert, limit=1)
        return matches[0] if matches else None


def suggest_templates(
    templates: list[IncidentTemplate],
    title: str,
    description: str | None = None,
    service: str | None = None,
    source: str | None = None,
    tags: list[str] | None = None,
    limit: int = 5,
) -> list[TemplateMatch]:
    """Convenience function to suggest templates for an alert."""
    alert = AlertData(
        title=title,
        description=description,
        service=service,
        source=source,
        tags=tags,
    )
    matcher = TemplateMatcher(templates)
    return matcher.match(alert, limit=limit)
