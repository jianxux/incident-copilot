"""AI-powered postmortem generation using Claude."""

import json
import uuid
from datetime import datetime

import structlog
from anthropic import AsyncAnthropic

from ..config import Settings, get_settings
from ..models import ContextCard
from .models import (
    ActionItem,
    ActionItemPriority,
    ActionItemStatus,
    ImpactAssessment,
    Postmortem,
    PostmortemStatus,
    RootCauseAnalysis,
    TimelineEvent,
    TimelineEventType,
)

logger = structlog.get_logger()


TIMELINE_PROMPT = """You are an expert SRE analyzing an incident. Generate a timeline of events from the provided context.

Incident: {title}
Service: {service_name}
Severity: {severity}
Triggered At: {triggered_at}

Context:
{context}

Generate a timeline with key events. For each event, provide:
- timestamp (ISO format)
- event_type: one of [alert_triggered, alert_acknowledged, investigation_started, root_cause_identified, mitigation_started, mitigation_completed, incident_resolved, deployment, configuration_change, escalation, communication, other]
- title: brief description
- description: optional details
- actor: who performed the action (if known)
- source: where this info came from (e.g., "datadog_logs", "github_deploy", "slack")

Respond ONLY with a JSON array of timeline events, ordered chronologically.
Example:
[
  {{"timestamp": "2024-01-15T10:00:00Z", "event_type": "alert_triggered", "title": "High error rate alert fired", "source": "pagerduty"}},
  {{"timestamp": "2024-01-15T10:05:00Z", "event_type": "investigation_started", "title": "On-call engineer started investigation", "actor": "jane.doe"}}
]"""


ROOT_CAUSE_PROMPT = """You are an expert SRE performing root cause analysis for an incident.

Incident: {title}
Service: {service_name}
Severity: {severity}

Timeline of events:
{timeline}

Context (logs, deploys, metrics):
{context}

Analyze this incident and provide a root cause analysis. Respond with a JSON object:
{{
  "primary_cause": "The main technical cause of the incident",
  "contributing_factors": ["Factor 1", "Factor 2"],
  "trigger": "What specific event triggered the incident",
  "detection_method": "How the incident was detected",
  "why_not_prevented": "Why existing safeguards didn't prevent this",
  "confidence_level": "high|medium|low"
}}

Be specific and technical. Focus on the root cause, not symptoms."""


IMPACT_PROMPT = """You are an expert SRE assessing the impact of an incident.

Incident: {title}
Service: {service_name}
Severity: {severity}
Duration: {duration_info}

Context:
{context}

Assess the impact of this incident. Respond with a JSON object:
{{
  "severity": "critical|high|medium|low",
  "duration_minutes": <integer or null>,
  "users_affected": <integer or null>,
  "users_affected_description": "Description of user impact",
  "revenue_impact": "Estimated revenue impact or null",
  "data_loss": true|false,
  "data_loss_description": "Details if data was lost or null",
  "sla_breach": true|false,
  "sla_breach_description": "SLA breach details or null",
  "regions_affected": ["region1", "region2"],
  "services_affected": ["service1", "service2"],
  "summary": "Brief impact summary"
}}

Be factual. Use null for unknown values rather than guessing."""


ACTION_ITEMS_PROMPT = """You are an expert SRE generating follow-up action items after an incident.

Incident: {title}
Service: {service_name}

Root Cause:
{root_cause}

Impact:
{impact}

Timeline Summary:
{timeline_summary}

Generate 3-7 actionable follow-up items to prevent recurrence and improve reliability. Categories:
- prevention: Prevent this exact issue
- detection: Improve detection/alerting
- mitigation: Reduce impact if it happens again
- process: Improve incident response process
- documentation: Update runbooks/docs

Respond with a JSON array:
[
  {{
    "title": "Short action title",
    "description": "Detailed description of what needs to be done",
    "priority": "critical|high|medium|low",
    "category": "prevention|detection|mitigation|process|documentation"
  }}
]

Focus on concrete, actionable items. Prioritize based on impact and effort."""


SUMMARY_PROMPT = """You are an expert SRE writing an executive summary for a postmortem.

Incident: {title}
Service: {service_name}
Severity: {severity}
Duration: {duration_info}

Root Cause: {root_cause}

Impact: {impact}

Key Timeline Events:
{timeline_summary}

Write a concise executive summary (2-4 paragraphs) that covers:
1. What happened (brief description)
2. Impact to users/business
3. Root cause
4. Key remediation steps taken and planned

Write in past tense. Be clear and factual. Target audience is engineering leadership.

Respond with just the summary text, no JSON."""


LESSONS_PROMPT = """You are an expert SRE reflecting on lessons learned from an incident.

Incident: {title}
Service: {service_name}

Root Cause: {root_cause}
Impact: {impact}

Timeline Summary:
{timeline_summary}

Generate a reflection on this incident. Respond with JSON:
{{
  "lessons_learned": ["Lesson 1", "Lesson 2", ...],
  "what_went_well": ["Thing 1", "Thing 2", ...],
  "what_went_poorly": ["Thing 1", "Thing 2", ...],
  "lucky_factors": ["Factor 1", ...]
}}

Be honest and constructive. Focus on systemic improvements, not blame.
"lucky_factors" are things that reduced impact by chance (e.g., "happened during low-traffic hours")."""


class PostmortemGenerator:
    """AI-powered postmortem generator using Claude."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = (
            AsyncAnthropic(api_key=self.settings.anthropic_api_key)
            if self.settings.anthropic_api_key
            else None
        )
        self.model = self.settings.ai_model

    async def generate(
        self,
        incident_id: str,
        context_card: ContextCard,
        include_ai_analysis: bool = True,
    ) -> Postmortem:
        """
        Generate a complete postmortem from incident context.

        Args:
            incident_id: The incident ID
            context_card: Assembled context card with logs, deploys, etc.
            include_ai_analysis: Whether to use AI for analysis (vs skeleton only)

        Returns:
            A complete Postmortem object
        """
        postmortem_id = f"pm-{uuid.uuid4().hex[:12]}"

        logger.info(
            "postmortem_generation_started",
            postmortem_id=postmortem_id,
            incident_id=incident_id,
            ai_enabled=include_ai_analysis and self.client is not None,
        )

        # Build context string from context card
        context_str = self._build_context_string(context_card)

        # Generate timeline
        timeline = []
        if include_ai_analysis and self.client:
            timeline = await self._generate_timeline(context_card, context_str)
        else:
            # Create basic timeline from available data
            timeline = self._create_basic_timeline(context_card)

        # Generate root cause analysis
        root_cause = None
        if include_ai_analysis and self.client:
            root_cause = await self._generate_root_cause(
                context_card, timeline, context_str
            )

        # Generate impact assessment
        impact = None
        if include_ai_analysis and self.client:
            impact = await self._generate_impact(context_card, context_str)

        # Generate action items
        action_items = []
        if include_ai_analysis and self.client and root_cause and impact:
            action_items = await self._generate_action_items(
                context_card, root_cause, impact, timeline
            )

        # Generate executive summary
        executive_summary = f"Incident affecting {context_card.service_name}"
        if include_ai_analysis and self.client and root_cause and impact:
            executive_summary = await self._generate_summary(
                context_card, root_cause, impact, timeline
            )

        # Generate lessons learned
        lessons_learned = []
        what_went_well = []
        what_went_poorly = []
        lucky_factors = []
        if include_ai_analysis and self.client and root_cause and impact:
            lessons = await self._generate_lessons(
                context_card, root_cause, impact, timeline
            )
            lessons_learned = lessons.get("lessons_learned", [])
            what_went_well = lessons.get("what_went_well", [])
            what_went_poorly = lessons.get("what_went_poorly", [])
            lucky_factors = lessons.get("lucky_factors", [])

        # Calculate duration if we have resolution time
        duration_minutes = None
        resolved_at = None
        for event in reversed(timeline):
            if event.event_type == TimelineEventType.INCIDENT_RESOLVED:
                resolved_at = event.timestamp
                break

        if resolved_at and context_card.triggered_at:
            duration_minutes = int(
                (resolved_at - context_card.triggered_at).total_seconds() / 60
            )

        postmortem = Postmortem(
            id=postmortem_id,
            incident_id=incident_id,
            title=f"Postmortem: {context_card.title}",
            status=PostmortemStatus.DRAFT,
            service_name=context_card.service_name,
            severity=context_card.severity.value,
            executive_summary=executive_summary,
            timeline=timeline,
            root_cause=root_cause,
            impact=impact,
            action_items=action_items,
            lessons_learned=lessons_learned,
            what_went_well=what_went_well,
            what_went_poorly=what_went_poorly,
            lucky_factors=lucky_factors,
            incident_started_at=context_card.triggered_at,
            incident_resolved_at=resolved_at,
            incident_duration_minutes=duration_minutes,
            alert_url=context_card.alert_url,
            dashboard_url=context_card.dashboard_url,
            ai_generated=include_ai_analysis and self.client is not None,
            ai_model=self.model if self.client else None,
            ai_confidence=0.7 if self.client else None,  # Default confidence
        )

        logger.info(
            "postmortem_generation_completed",
            postmortem_id=postmortem_id,
            incident_id=incident_id,
            timeline_events=len(timeline),
            action_items=len(action_items),
        )

        return postmortem

    async def update_incrementally(
        self,
        postmortem: Postmortem,
        context_card: ContextCard,
        sections: list[str] | None = None,
    ) -> Postmortem:
        """
        Incrementally update a postmortem with new context.

        Args:
            postmortem: Existing postmortem to update
            context_card: Updated context card
            sections: Specific sections to update (or all if None)

        Returns:
            Updated Postmortem object
        """
        sections = sections or ["timeline", "root_cause", "impact", "action_items"]
        context_str = self._build_context_string(context_card)

        if "timeline" in sections:
            new_timeline = await self._generate_timeline(context_card, context_str)
            # Merge timelines, avoiding duplicates
            existing_timestamps = {e.timestamp for e in postmortem.timeline}
            for event in new_timeline:
                if event.timestamp not in existing_timestamps:
                    postmortem.timeline.append(event)
            postmortem.timeline.sort(key=lambda e: e.timestamp)

        if "root_cause" in sections and self.client:
            postmortem.root_cause = await self._generate_root_cause(
                context_card, postmortem.timeline, context_str
            )

        if "impact" in sections and self.client:
            postmortem.impact = await self._generate_impact(context_card, context_str)

        if "action_items" in sections and postmortem.root_cause and postmortem.impact:
            postmortem.action_items = await self._generate_action_items(
                context_card,
                postmortem.root_cause,
                postmortem.impact,
                postmortem.timeline,
            )

        postmortem.updated_at = datetime.utcnow()
        postmortem.version += 1

        return postmortem

    def _build_context_string(self, context_card: ContextCard) -> str:
        """Build a context string from the context card for AI prompts."""
        parts = []

        # GitHub context
        if context_card.github:
            parts.append("## Recent Deployments (GitHub)")
            for deploy in context_card.github.recent_deploys[:5]:
                parts.append(
                    f"- {deploy.timestamp.isoformat()}: {deploy.short_sha} by {deploy.author}"
                )
                parts.append(f"  Message: {deploy.message[:100]}")

        # GitLab context
        if context_card.gitlab:
            parts.append("## Recent Deployments (GitLab)")
            for deploy in context_card.gitlab.recent_deploys[:5]:
                parts.append(
                    f"- {deploy.timestamp.isoformat()}: {deploy.short_sha} by {deploy.author}"
                )
                parts.append(f"  Message: {deploy.message[:100]}")

        # Datadog context
        if context_card.datadog:
            parts.append("## Datadog Metrics")
            if context_card.datadog.metrics:
                m = context_card.datadog.metrics
                parts.append(f"- Error rate: {m.error_rate}")
                parts.append(f"- P99 latency: {m.latency_p99_ms}ms")

            parts.append("## Log Summaries")
            for summary in context_card.datadog.log_summaries[:5]:
                parts.append(
                    f"- [{summary.level}] {summary.pattern} (count: {summary.count})"
                )

        # AI Summary
        if context_card.ai_summary:
            parts.append("## AI Log Analysis")
            parts.append(f"Explanation: {context_card.ai_summary.explanation}")
            if context_card.ai_summary.likely_cause:
                parts.append(f"Likely cause: {context_card.ai_summary.likely_cause}")
            parts.append("Top issues:")
            for issue in context_card.ai_summary.top_issues:
                parts.append(f"- {issue}")

        # Similar incidents
        if context_card.similar_incidents:
            parts.append("## Similar Past Incidents")
            for incident in context_card.similar_incidents[:3]:
                parts.append(f"- {incident.title}")
                if incident.root_cause:
                    parts.append(f"  Root cause: {incident.root_cause}")

        return "\n".join(parts) if parts else "No additional context available."

    def _create_basic_timeline(self, context_card: ContextCard) -> list[TimelineEvent]:
        """Create a basic timeline from available structured data."""
        timeline = []

        # Alert triggered
        timeline.append(
            TimelineEvent(
                timestamp=context_card.triggered_at,
                event_type=TimelineEventType.ALERT_TRIGGERED,
                title=context_card.title,
                source="alert",
            )
        )

        # Add deployments
        if context_card.github:
            for deploy in context_card.github.recent_deploys[:3]:
                if deploy.timestamp < context_card.triggered_at:
                    timeline.append(
                        TimelineEvent(
                            timestamp=deploy.timestamp,
                            event_type=TimelineEventType.DEPLOYMENT,
                            title=f"Deployment: {deploy.short_sha}",
                            description=deploy.message[:200],
                            actor=deploy.author,
                            source="github",
                        )
                    )

        if context_card.gitlab:
            for deploy in context_card.gitlab.recent_deploys[:3]:
                if deploy.timestamp < context_card.triggered_at:
                    timeline.append(
                        TimelineEvent(
                            timestamp=deploy.timestamp,
                            event_type=TimelineEventType.DEPLOYMENT,
                            title=f"Deployment: {deploy.short_sha}",
                            description=deploy.message[:200],
                            actor=deploy.author,
                            source="gitlab",
                        )
                    )

        # Sort by timestamp
        timeline.sort(key=lambda e: e.timestamp)
        return timeline

    async def _generate_timeline(
        self, context_card: ContextCard, context_str: str
    ) -> list[TimelineEvent]:
        """Generate timeline using AI."""
        if not self.client:
            return self._create_basic_timeline(context_card)

        try:
            prompt = TIMELINE_PROMPT.format(
                title=context_card.title,
                service_name=context_card.service_name,
                severity=context_card.severity.value,
                triggered_at=context_card.triggered_at.isoformat(),
                context=context_str,
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            data = json.loads(content)

            timeline = []
            for event_data in data:
                event_type = TimelineEventType.OTHER
                try:
                    event_type = TimelineEventType(
                        event_data.get("event_type", "other")
                    )
                except ValueError:
                    pass

                timeline.append(
                    TimelineEvent(
                        timestamp=datetime.fromisoformat(
                            event_data["timestamp"].replace("Z", "+00:00")
                        ),
                        event_type=event_type,
                        title=event_data["title"],
                        description=event_data.get("description"),
                        actor=event_data.get("actor"),
                        source=event_data.get("source"),
                    )
                )

            return timeline

        except Exception as e:
            logger.error("timeline_generation_failed", error=str(e))
            return self._create_basic_timeline(context_card)

    async def _generate_root_cause(
        self,
        context_card: ContextCard,
        timeline: list[TimelineEvent],
        context_str: str,
    ) -> RootCauseAnalysis | None:
        """Generate root cause analysis using AI."""
        if not self.client:
            return None

        try:
            timeline_str = "\n".join(
                f"- {e.timestamp.isoformat()}: {e.title}" for e in timeline
            )

            prompt = ROOT_CAUSE_PROMPT.format(
                title=context_card.title,
                service_name=context_card.service_name,
                severity=context_card.severity.value,
                timeline=timeline_str,
                context=context_str,
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            data = json.loads(content)

            return RootCauseAnalysis(
                primary_cause=data["primary_cause"],
                contributing_factors=data.get("contributing_factors", []),
                trigger=data.get("trigger"),
                detection_method=data.get("detection_method"),
                why_not_prevented=data.get("why_not_prevented"),
                confidence_level=data.get("confidence_level", "medium"),
            )

        except Exception as e:
            logger.error("root_cause_generation_failed", error=str(e))
            return None

    async def _generate_impact(
        self, context_card: ContextCard, context_str: str
    ) -> ImpactAssessment | None:
        """Generate impact assessment using AI."""
        if not self.client:
            return None

        try:
            duration_info = "Unknown duration"
            if context_card.datadog and context_card.datadog.metrics:
                duration_info = (
                    f"{context_card.datadog.metrics.time_range_minutes} minutes of data"
                )

            prompt = IMPACT_PROMPT.format(
                title=context_card.title,
                service_name=context_card.service_name,
                severity=context_card.severity.value,
                duration_info=duration_info,
                context=context_str,
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            data = json.loads(content)

            return ImpactAssessment(
                severity=data.get("severity", context_card.severity.value),
                duration_minutes=data.get("duration_minutes"),
                users_affected=data.get("users_affected"),
                users_affected_description=data.get("users_affected_description"),
                revenue_impact=data.get("revenue_impact"),
                data_loss=data.get("data_loss", False),
                data_loss_description=data.get("data_loss_description"),
                sla_breach=data.get("sla_breach", False),
                sla_breach_description=data.get("sla_breach_description"),
                regions_affected=data.get("regions_affected", []),
                services_affected=data.get("services_affected", []),
                summary=data.get("summary"),
            )

        except Exception as e:
            logger.error("impact_generation_failed", error=str(e))
            return None

    async def _generate_action_items(
        self,
        context_card: ContextCard,
        root_cause: RootCauseAnalysis,
        impact: ImpactAssessment,
        timeline: list[TimelineEvent],
    ) -> list[ActionItem]:
        """Generate action items using AI."""
        if not self.client:
            return []

        try:
            timeline_summary = "\n".join(f"- {e.title}" for e in timeline[:10])

            prompt = ACTION_ITEMS_PROMPT.format(
                title=context_card.title,
                service_name=context_card.service_name,
                root_cause=root_cause.primary_cause,
                impact=impact.summary or f"{impact.severity} severity incident",
                timeline_summary=timeline_summary,
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            data = json.loads(content)

            action_items = []
            for i, item_data in enumerate(data):
                priority = ActionItemPriority.MEDIUM
                try:
                    priority = ActionItemPriority(item_data.get("priority", "medium"))
                except ValueError:
                    pass

                action_items.append(
                    ActionItem(
                        id=f"ai-{uuid.uuid4().hex[:8]}",
                        title=item_data["title"],
                        description=item_data.get("description"),
                        priority=priority,
                        status=ActionItemStatus.TODO,
                        category=item_data.get("category"),
                    )
                )

            return action_items

        except Exception as e:
            logger.error("action_items_generation_failed", error=str(e))
            return []

    async def _generate_summary(
        self,
        context_card: ContextCard,
        root_cause: RootCauseAnalysis,
        impact: ImpactAssessment,
        timeline: list[TimelineEvent],
    ) -> str:
        """Generate executive summary using AI."""
        if not self.client:
            return f"Incident affecting {context_card.service_name}"

        try:
            timeline_summary = "\n".join(
                f"- {e.timestamp.strftime('%H:%M')}: {e.title}" for e in timeline[:8]
            )

            duration_info = "Duration unknown"
            if impact.duration_minutes:
                duration_info = f"{impact.duration_minutes} minutes"

            prompt = SUMMARY_PROMPT.format(
                title=context_card.title,
                service_name=context_card.service_name,
                severity=context_card.severity.value,
                duration_info=duration_info,
                root_cause=root_cause.primary_cause,
                impact=impact.summary or f"{impact.severity} severity",
                timeline_summary=timeline_summary,
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            return response.content[0].text.strip()

        except Exception as e:
            logger.error("summary_generation_failed", error=str(e))
            return f"Incident affecting {context_card.service_name}"

    async def _generate_lessons(
        self,
        context_card: ContextCard,
        root_cause: RootCauseAnalysis,
        impact: ImpactAssessment,
        timeline: list[TimelineEvent],
    ) -> dict:
        """Generate lessons learned using AI."""
        if not self.client:
            return {}

        try:
            timeline_summary = "\n".join(f"- {e.title}" for e in timeline[:10])

            prompt = LESSONS_PROMPT.format(
                title=context_card.title,
                service_name=context_card.service_name,
                root_cause=root_cause.primary_cause,
                impact=impact.summary or f"{impact.severity} severity",
                timeline_summary=timeline_summary,
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            return json.loads(content)

        except Exception as e:
            logger.error("lessons_generation_failed", error=str(e))
            return {}
