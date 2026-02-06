"""Auto-suggest templates based on alert content."""

import re
from collections import Counter

import structlog

from .models import IncidentTemplate, TemplateCategory, TemplateMatch
from .store import template_store

logger = structlog.get_logger()

# Stopwords to filter out during keyword extraction
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
    "from", "as", "into", "through", "during", "before", "after", "above",
    "below", "between", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "and", "but", "if", "or",
    "because", "until", "while", "this", "that", "these", "those", "it",
    "its", "alert", "incident", "triggered", "fired", "resolved",
}


class TemplateMatcher:
    """Match incident templates based on alert content and context."""

    def __init__(self):
        self._keyword_weights: dict[str, float] = {}
        self._category_keywords: dict[TemplateCategory, set[str]] = {
            TemplateCategory.DATABASE: {
                "database", "db", "sql", "mysql", "postgres", "postgresql",
                "mongodb", "redis", "connection", "pool", "query", "deadlock",
                "replication", "slave", "master", "primary", "replica",
                "transaction", "lock", "timeout", "slow query",
            },
            TemplateCategory.INFRASTRUCTURE: {
                "cpu", "memory", "disk", "storage", "node", "server", "host",
                "instance", "vm", "container", "kubernetes", "k8s", "pod",
                "deployment", "scaling", "autoscaling", "capacity", "resource",
            },
            TemplateCategory.NETWORK: {
                "network", "dns", "latency", "timeout", "connection", "tcp",
                "udp", "http", "https", "ssl", "tls", "certificate", "firewall",
                "load balancer", "lb", "proxy", "nginx", "haproxy", "routing",
            },
            TemplateCategory.APPLICATION: {
                "error", "exception", "crash", "oom", "memory leak", "bug",
                "deployment", "release", "rollback", "service", "api",
                "request", "response", "5xx", "4xx", "500", "502", "503",
            },
            TemplateCategory.SECURITY: {
                "security", "auth", "authentication", "authorization",
                "permission", "access", "denied", "forbidden", "unauthorized",
                "breach", "attack", "ddos", "intrusion", "vulnerability",
            },
            TemplateCategory.OBSERVABILITY: {
                "monitoring", "metrics", "logs", "traces", "alerting",
                "dashboard", "grafana", "prometheus", "datadog", "splunk",
            },
            TemplateCategory.CLOUD: {
                "aws", "azure", "gcp", "cloud", "lambda", "function",
                "s3", "ec2", "rds", "eks", "ecs", "cloudfront", "route53",
            },
        }

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text."""
        # Lowercase and split on non-alphanumeric
        words = re.findall(r"[a-zA-Z0-9_-]+", text.lower())
        
        # Filter stopwords and short words
        keywords = [w for w in words if w not in STOPWORDS and len(w) > 2]
        
        return keywords

    def _compute_relevance_score(
        self,
        template: IncidentTemplate,
        query_keywords: set[str],
        service_name: str | None = None,
        severity: str | None = None,
    ) -> tuple[float, list[str], list[str], bool]:
        """
        Compute relevance score for a template.
        
        Returns: (score, matched_keywords, matched_services, severity_matched)
        """
        score = 0.0
        matched_keywords = []
        matched_services = []
        severity_matched = False
        
        # Keyword matching (weight: 0.4)
        template_keywords = {k.lower() for k in template.keywords}
        keyword_matches = query_keywords & template_keywords
        if keyword_matches:
            keyword_score = len(keyword_matches) / max(len(template_keywords), 1)
            score += keyword_score * 0.4
            matched_keywords = list(keyword_matches)
        
        # Also check for partial matches in template name and description
        name_desc_text = f"{template.name} {template.description}".lower()
        for kw in query_keywords:
            if kw in name_desc_text and kw not in matched_keywords:
                score += 0.05
                matched_keywords.append(kw)
        
        # Service tag matching (weight: 0.35)
        if service_name:
            service_lower = service_name.lower()
            for tag in template.service_tags:
                tag_lower = tag.lower()
                if tag_lower in service_lower or service_lower in tag_lower:
                    score += 0.35
                    matched_services.append(tag)
                    break
                # Partial match
                elif any(part in service_lower for part in tag_lower.split("-")):
                    score += 0.2
                    matched_services.append(tag)
        
        # Severity matching (weight: 0.25)
        if severity and template.severity_levels:
            severity_lower = severity.lower()
            if severity_lower in [s.lower() for s in template.severity_levels]:
                score += 0.25
                severity_matched = True
        
        # Category bonus: boost if query keywords match category keywords
        category_kws = self._category_keywords.get(template.category, set())
        category_matches = query_keywords & category_kws
        if category_matches:
            score += min(len(category_matches) * 0.05, 0.15)
        
        # Normalize score to [0, 1]
        score = min(score, 1.0)
        
        return score, matched_keywords, matched_services, severity_matched

    async def find_matching_templates(
        self,
        query: str,
        service_name: str | None = None,
        severity: str | None = None,
        tags: list[str] | None = None,
        tenant_id: str | None = None,
        min_score: float = 0.1,
        top_k: int = 5,
    ) -> list[TemplateMatch]:
        """
        Find templates matching the given alert/incident context.
        
        Args:
            query: Alert title, description, or combined text
            service_name: Name of the affected service
            severity: Incident severity level
            tags: Additional tags from the alert
            tenant_id: Tenant ID for multi-tenant filtering
            min_score: Minimum relevance score threshold
            top_k: Maximum number of templates to return
        
        Returns:
            List of TemplateMatch objects sorted by relevance
        """
        # Extract keywords from query
        query_keywords = set(self._extract_keywords(query))
        
        # Add tags to keywords if provided
        if tags:
            for tag in tags:
                query_keywords.update(self._extract_keywords(tag))
        
        logger.debug(
            "template_matching_started",
            query_keywords=list(query_keywords),
            service_name=service_name,
            severity=severity,
        )
        
        # Get all applicable templates
        templates = await template_store.list(
            tenant_id=tenant_id,
            include_builtin=True,
            enabled_only=True,
            limit=500,
        )
        
        matches: list[TemplateMatch] = []
        
        for template in templates:
            score, matched_kw, matched_svc, sev_matched = self._compute_relevance_score(
                template=template,
                query_keywords=query_keywords,
                service_name=service_name,
                severity=severity,
            )
            
            if score >= min_score:
                matches.append(TemplateMatch(
                    template_id=template.id,
                    template_name=template.name,
                    category=template.category,
                    description=template.description,
                    relevance_score=round(score, 3),
                    matched_keywords=matched_kw,
                    matched_services=matched_svc,
                    matched_severity=sev_matched,
                    step_count=len(template.steps),
                    total_time_estimate_minutes=template.total_time_estimate_minutes,
                ))
        
        # Sort by relevance score descending
        matches.sort(key=lambda m: m.relevance_score, reverse=True)
        
        logger.info(
            "template_matching_completed",
            query_length=len(query),
            templates_checked=len(templates),
            matches_found=len(matches),
            top_match=matches[0].template_name if matches else None,
        )
        
        return matches[:top_k]

    async def auto_suggest(
        self,
        alert_title: str,
        alert_description: str | None = None,
        service_name: str | None = None,
        severity: str | None = None,
        tags: list[str] | None = None,
        tenant_id: str | None = None,
    ) -> TemplateMatch | None:
        """
        Automatically suggest the best matching template for an alert.
        
        Returns the top match if score >= 0.3, otherwise None.
        """
        query = alert_title
        if alert_description:
            query = f"{alert_title} {alert_description}"
        
        matches = await self.find_matching_templates(
            query=query,
            service_name=service_name,
            severity=severity,
            tags=tags,
            tenant_id=tenant_id,
            min_score=0.3,
            top_k=1,
        )
        
        if matches:
            logger.info(
                "template_auto_suggested",
                template_id=matches[0].template_id,
                template_name=matches[0].template_name,
                score=matches[0].relevance_score,
            )
            return matches[0]
        
        return None

    def infer_category(self, text: str) -> TemplateCategory | None:
        """Infer the most likely category from text."""
        text_lower = text.lower()
        keywords = set(self._extract_keywords(text_lower))
        
        category_scores: Counter[TemplateCategory] = Counter()
        
        for category, cat_keywords in self._category_keywords.items():
            matches = keywords & cat_keywords
            if matches:
                category_scores[category] = len(matches)
        
        if category_scores:
            return category_scores.most_common(1)[0][0]
        
        return None


# Global matcher instance
template_matcher = TemplateMatcher()
