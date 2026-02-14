"""AI Verdict Engine - Generates opinionated root cause verdicts for incidents.

Instead of just summarizing logs, the verdict engine produces a single,
confident assessment: what's most likely wrong and what to do RIGHT NOW.
"""

import json
from datetime import datetime
from enum import StrEnum

import structlog
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from ..config import Settings

logger = structlog.get_logger()


class ConfidenceLevel(StrEnum):
    """How confident the AI is in its verdict."""

    HIGH = "high"  # Strong signal — deploy correlation, clear error pattern
    MEDIUM = "medium"  # Reasonable hypothesis but needs verification
    LOW = "low"  # Weak signal — investigating


class Verdict(BaseModel):
    """The AI's opinionated assessment of an incident."""

    # The single most likely cause — one bold sentence
    most_likely_cause: str

    # Confidence in the verdict
    confidence: ConfidenceLevel

    # Why the AI thinks this (one sentence of evidence)
    evidence: str

    # THE one thing to do right now — not a list, a single action
    recommended_action: str

    # Optional: second action if relevant (keep it to max 2)
    secondary_action: str | None = None

    # Was this correlated with a recent deployment?
    deploy_correlated: bool = False

    # If deploy correlated, which deploy
    suspect_deploy: str | None = None

    # Generated at
    generated_at: datetime = Field(default_factory=datetime.utcnow)


VERDICT_PROMPT = """You are a senior SRE making a FAST call during a live incident. You have 10 seconds to tell the on-call engineer what's wrong and what to do.

INCIDENT: {title}
SERVICE: {service_name}
SEVERITY: {severity}
TRIGGERED: {triggered_at}

{context_sections}

Based on ALL the evidence above, give your VERDICT. Be opinionated. Be decisive. If a recent deploy looks suspicious, call it out directly.

Respond with ONLY this JSON:
{{
  "most_likely_cause": "One bold sentence. What is most likely broken and why.",
  "confidence": "high|medium|low",
  "evidence": "One sentence: the key data point that supports your verdict.",
  "recommended_action": "THE one thing to do RIGHT NOW. Be specific (e.g., 'Roll back deploy abc123' not 'investigate').",
  "secondary_action": "Optional second action, or null.",
  "deploy_correlated": true/false,
  "suspect_deploy": "commit SHA or null"
}}

Rules:
- If there's a deploy in the last 2 hours that touches the affected service, assume it's the cause unless evidence says otherwise. Say so with HIGH confidence.
- "Investigate further" is NOT an acceptable recommended_action. Give a SPECIFIC action.
- Keep most_likely_cause under 30 words.
- Keep recommended_action under 25 words."""


class VerdictEngine:
    """Generates opinionated AI verdicts for incidents."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            AsyncAnthropic(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )
        self.model = settings.ai_model

    async def generate_verdict(
        self,
        title: str,
        service_name: str,
        severity: str,
        triggered_at: datetime,
        recent_deploys: list[dict] | None = None,
        log_summary: dict | None = None,
        metrics: dict | None = None,
        similar_incidents: list[dict] | None = None,
        topology: dict | None = None,
    ) -> Verdict | None:
        """Generate an opinionated verdict from available context.

        Args:
            title: Incident title
            service_name: Affected service
            severity: Severity level
            triggered_at: When the alert fired
            recent_deploys: List of recent deployments (sha, author, message, timestamp)
            log_summary: AI log summary (top_issues, likely_cause, etc.)
            metrics: Metric snapshots (error_rate, latency, etc.)
            similar_incidents: Past similar incidents
            topology: Service dependency context

        Returns:
            Verdict with cause, confidence, and recommended action
        """
        if not self.client:
            logger.warning(
                "verdict_engine_no_client", reason="anthropic_not_configured"
            )
            return self._fallback_verdict(
                title, service_name, recent_deploys, log_summary
            )

        # Build context sections
        context_sections = self._build_context_sections(
            recent_deploys=recent_deploys,
            log_summary=log_summary,
            metrics=metrics,
            similar_incidents=similar_incidents,
            topology=topology,
        )

        prompt = VERDICT_PROMPT.format(
            title=title,
            service_name=service_name,
            severity=severity,
            triggered_at=triggered_at.isoformat(),
            context_sections=context_sections,
        )

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            content = "".join(getattr(block, "text", "") for block in response.content)

            # Strip markdown code fences if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            content = content.strip()

            data = json.loads(content)

            verdict = Verdict(
                most_likely_cause=data["most_likely_cause"],
                confidence=ConfidenceLevel(data["confidence"]),
                evidence=data["evidence"],
                recommended_action=data["recommended_action"],
                secondary_action=data.get("secondary_action"),
                deploy_correlated=data.get("deploy_correlated", False),
                suspect_deploy=data.get("suspect_deploy"),
            )

            logger.info(
                "verdict_generated",
                service=service_name,
                confidence=verdict.confidence.value,
                deploy_correlated=verdict.deploy_correlated,
            )

            return verdict

        except Exception as e:
            logger.error("verdict_generation_failed", error=str(e))
            return self._fallback_verdict(
                title, service_name, recent_deploys, log_summary
            )

    def _build_context_sections(
        self,
        recent_deploys: list[dict] | None = None,
        log_summary: dict | None = None,
        metrics: dict | None = None,
        similar_incidents: list[dict] | None = None,
        topology: dict | None = None,
    ) -> str:
        """Build formatted context sections for the prompt."""
        sections = []

        if recent_deploys:
            lines = ["RECENT DEPLOYMENTS:"]
            for d in recent_deploys[:5]:
                lines.append(
                    f"  - {d.get('short_sha', d.get('sha', '?')[:7])} by {d.get('author', '?')} "
                    f"at {d.get('timestamp', '?')} — {d.get('message', '')[:80]}"
                )
                if d.get("files_changed"):
                    lines.append(f"    Files: {', '.join(d['files_changed'][:5])}")
            sections.append("\n".join(lines))

        if log_summary:
            lines = ["LOG ANALYSIS:"]
            if log_summary.get("top_issues"):
                for issue in log_summary["top_issues"][:5]:
                    lines.append(f"  - {issue}")
            if log_summary.get("likely_cause"):
                lines.append(f"  Likely cause: {log_summary['likely_cause']}")
            if log_summary.get("explanation"):
                lines.append(f"  Explanation: {log_summary['explanation']}")
            sections.append("\n".join(lines))

        if metrics:
            lines = ["METRICS:"]
            if metrics.get("error_rate") is not None:
                baseline = metrics.get("error_rate_baseline")
                line = f"  Error rate: {metrics['error_rate']:.1%}"
                if baseline is not None:
                    line += f" (baseline: {baseline:.1%})"
                lines.append(line)
            if metrics.get("latency_p99_ms") is not None:
                lines.append(f"  P99 latency: {metrics['latency_p99_ms']:.0f}ms")
            if metrics.get("request_count") is not None:
                lines.append(f"  Request count (5m): {metrics['request_count']}")
            sections.append("\n".join(lines))

        if similar_incidents:
            lines = ["SIMILAR PAST INCIDENTS:"]
            for inc in similar_incidents[:3]:
                line = f"  - {inc.get('title', '?')} ({inc.get('occurred_at', '?')})"
                if inc.get("root_cause"):
                    line += f"\n    Root cause: {inc['root_cause']}"
                if inc.get("resolution"):
                    line += f"\n    Resolution: {inc['resolution']}"
                lines.append(line)
            sections.append("\n".join(lines))

        if topology:
            lines = ["SERVICE TOPOLOGY:"]
            if topology.get("blast_radius_count"):
                lines.append(
                    f"  Blast radius: {topology['blast_radius_count']} services affected"
                )
            if topology.get("critical_services_affected"):
                lines.append(
                    f"  Critical: {', '.join(topology['critical_services_affected'])}"
                )
            if topology.get("upstream_services"):
                lines.append(
                    f"  Depends on: {', '.join(topology['upstream_services'][:5])}"
                )
            sections.append("\n".join(lines))

        return "\n\n".join(sections) if sections else "No additional context available."

    def _fallback_verdict(
        self,
        title: str,
        service_name: str,
        recent_deploys: list[dict] | None = None,
        log_summary: dict | None = None,
    ) -> Verdict:
        """Generate a rule-based fallback verdict when AI is unavailable."""
        # Simple heuristic: if there's a recent deploy, blame it
        if recent_deploys:
            deploy = recent_deploys[0]
            return Verdict(
                most_likely_cause=(
                    f"Recent deployment {deploy.get('short_sha', '?')[:7]} by "
                    f"{deploy.get('author', '?')} may have introduced the issue."
                ),
                confidence=ConfidenceLevel.MEDIUM,
                evidence=f"Deploy occurred shortly before alert: {deploy.get('message', '')[:60]}",
                recommended_action=(
                    f"Roll back deploy {deploy.get('short_sha', deploy.get('sha', '?'))[:7]} "
                    f"and verify if the issue resolves."
                ),
                deploy_correlated=True,
                suspect_deploy=deploy.get("short_sha", deploy.get("sha")),
            )

        # Use log summary if available
        if log_summary and log_summary.get("likely_cause"):
            return Verdict(
                most_likely_cause=log_summary["likely_cause"],
                confidence=ConfidenceLevel.LOW,
                evidence=log_summary.get("explanation", "Based on error log patterns."),
                recommended_action=(
                    log_summary.get(
                        "suggested_actions", ["Check service logs and metrics"]
                    )[0]
                ),
            )

        # Bare minimum fallback
        return Verdict(
            most_likely_cause=f"Alert triggered on {service_name}: {title}",
            confidence=ConfidenceLevel.LOW,
            evidence="Insufficient context for confident diagnosis.",
            recommended_action=f"Check {service_name} dashboards and recent deployments immediately.",
        )
