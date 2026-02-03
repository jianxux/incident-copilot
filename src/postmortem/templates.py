"""Output format templates for postmortems."""

import json
from abc import ABC, abstractmethod
from datetime import datetime

from .models import (
    ActionItem,
    ImpactAssessment,
    Postmortem,
    PostmortemFormat,
    RootCauseAnalysis,
    TimelineEvent,
)


class BaseTemplate(ABC):
    """Base class for postmortem templates."""

    format: PostmortemFormat

    @abstractmethod
    def render(self, postmortem: Postmortem) -> str:
        """Render the postmortem in this format."""
        pass


class MarkdownTemplate(BaseTemplate):
    """Clean markdown output template."""

    format = PostmortemFormat.MARKDOWN

    def render(self, postmortem: Postmortem) -> str:
        """Render postmortem as Markdown."""
        lines = []

        # Header
        lines.append(f"# {postmortem.title}")
        lines.append("")
        lines.append(f"**Status:** {postmortem.status.value.replace('_', ' ').title()}")
        lines.append(f"**Service:** {postmortem.service_name}")
        lines.append(f"**Severity:** {postmortem.severity.upper()}")
        lines.append(
            f"**Date:** {postmortem.incident_started_at.strftime('%Y-%m-%d') if postmortem.incident_started_at else 'Unknown'}"
        )
        if postmortem.incident_duration_minutes:
            lines.append(
                f"**Duration:** {self._format_duration(postmortem.incident_duration_minutes)}"
            )
        lines.append("")

        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(postmortem.executive_summary)
        lines.append("")

        # Timeline
        if postmortem.timeline:
            lines.append("## Timeline")
            lines.append("")
            for event in postmortem.timeline:
                timestamp = event.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
                actor_str = f" ({event.actor})" if event.actor else ""
                lines.append(f"- **{timestamp}** - {event.title}{actor_str}")
                if event.description:
                    lines.append(f"  - {event.description}")
            lines.append("")

        # Root Cause Analysis
        if postmortem.root_cause:
            lines.append("## Root Cause Analysis")
            lines.append("")
            lines.append(f"**Primary Cause:** {postmortem.root_cause.primary_cause}")
            lines.append("")
            if postmortem.root_cause.trigger:
                lines.append(f"**Trigger:** {postmortem.root_cause.trigger}")
                lines.append("")
            if postmortem.root_cause.contributing_factors:
                lines.append("**Contributing Factors:**")
                for factor in postmortem.root_cause.contributing_factors:
                    lines.append(f"- {factor}")
                lines.append("")
            if postmortem.root_cause.detection_method:
                lines.append(
                    f"**Detection Method:** {postmortem.root_cause.detection_method}"
                )
                lines.append("")
            if postmortem.root_cause.why_not_prevented:
                lines.append(
                    f"**Why Not Prevented:** {postmortem.root_cause.why_not_prevented}"
                )
                lines.append("")
            lines.append(
                f"**Confidence Level:** {postmortem.root_cause.confidence_level.title()}"
            )
            lines.append("")

        # Impact Assessment
        if postmortem.impact:
            lines.append("## Impact Assessment")
            lines.append("")
            if postmortem.impact.summary:
                lines.append(postmortem.impact.summary)
                lines.append("")
            lines.append(f"- **Severity:** {postmortem.impact.severity.upper()}")
            if postmortem.impact.duration_minutes:
                lines.append(
                    f"- **Duration:** {self._format_duration(postmortem.impact.duration_minutes)}"
                )
            if postmortem.impact.users_affected:
                lines.append(
                    f"- **Users Affected:** {postmortem.impact.users_affected:,}"
                )
            if postmortem.impact.users_affected_description:
                lines.append(
                    f"- **User Impact:** {postmortem.impact.users_affected_description}"
                )
            if postmortem.impact.revenue_impact:
                lines.append(
                    f"- **Revenue Impact:** {postmortem.impact.revenue_impact}"
                )
            if postmortem.impact.sla_breach:
                lines.append(
                    f"- **SLA Breach:** Yes - {postmortem.impact.sla_breach_description or 'Details pending'}"
                )
            if postmortem.impact.data_loss:
                lines.append(
                    f"- **Data Loss:** Yes - {postmortem.impact.data_loss_description or 'Details pending'}"
                )
            if postmortem.impact.services_affected:
                lines.append(
                    f"- **Services Affected:** {', '.join(postmortem.impact.services_affected)}"
                )
            if postmortem.impact.regions_affected:
                lines.append(
                    f"- **Regions Affected:** {', '.join(postmortem.impact.regions_affected)}"
                )
            lines.append("")

        # Resolution Steps
        if postmortem.resolution_steps:
            lines.append("## Resolution Steps")
            lines.append("")
            for step in postmortem.resolution_steps:
                status = "✓" if step.successful else "✗"
                lines.append(f"{step.order}. {status} {step.description}")
            lines.append("")

        # Lessons Learned
        if postmortem.lessons_learned:
            lines.append("## Lessons Learned")
            lines.append("")
            for lesson in postmortem.lessons_learned:
                lines.append(f"- {lesson}")
            lines.append("")

        # What Went Well / Poorly
        if postmortem.what_went_well:
            lines.append("### What Went Well")
            lines.append("")
            for item in postmortem.what_went_well:
                lines.append(f"- {item}")
            lines.append("")

        if postmortem.what_went_poorly:
            lines.append("### What Went Poorly")
            lines.append("")
            for item in postmortem.what_went_poorly:
                lines.append(f"- {item}")
            lines.append("")

        if postmortem.lucky_factors:
            lines.append("### Where We Got Lucky")
            lines.append("")
            for item in postmortem.lucky_factors:
                lines.append(f"- {item}")
            lines.append("")

        # Action Items
        if postmortem.action_items:
            lines.append("## Action Items")
            lines.append("")
            lines.append("| Priority | Title | Status | Owner |")
            lines.append("|----------|-------|--------|-------|")
            for item in postmortem.action_items:
                owner = item.owner or "TBD"
                status = item.status.value.replace("_", " ").title()
                priority = item.priority.value.upper()
                lines.append(f"| {priority} | {item.title} | {status} | {owner} |")
            lines.append("")

        # Links
        links = []
        if postmortem.alert_url:
            links.append(f"- [Alert]({postmortem.alert_url})")
        if postmortem.dashboard_url:
            links.append(f"- [Dashboard]({postmortem.dashboard_url})")
        if postmortem.runbook_url:
            links.append(f"- [Runbook]({postmortem.runbook_url})")

        if links:
            lines.append("## Links")
            lines.append("")
            lines.extend(links)
            lines.append("")

        # Metadata
        lines.append("---")
        lines.append("")
        lines.append(f"*Postmortem ID: {postmortem.id}*")
        lines.append(f"*Incident ID: {postmortem.incident_id}*")
        if postmortem.ai_generated:
            lines.append(f"*AI Generated: {postmortem.ai_model}*")
        lines.append(
            f"*Last Updated: {postmortem.updated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}*"
        )

        return "\n".join(lines)

    def _format_duration(self, minutes: int) -> str:
        """Format duration in human-readable form."""
        if minutes < 60:
            return f"{minutes} minutes"
        hours = minutes // 60
        remaining_minutes = minutes % 60
        if remaining_minutes == 0:
            return f"{hours} hour{'s' if hours > 1 else ''}"
        return f"{hours}h {remaining_minutes}m"


class ConfluenceTemplate(BaseTemplate):
    """Confluence wiki markup template."""

    format = PostmortemFormat.CONFLUENCE

    def render(self, postmortem: Postmortem) -> str:
        """Render postmortem as Confluence wiki markup."""
        lines = []

        # Header with status macro
        lines.append(f"h1. {postmortem.title}")
        lines.append("")

        # Info panel
        lines.append("{info}")
        lines.append(f"*Service:* {postmortem.service_name}")
        lines.append(f"*Severity:* {postmortem.severity.upper()}")
        lines.append(f"*Status:* {postmortem.status.value.replace('_', ' ').title()}")
        if postmortem.incident_started_at:
            lines.append(
                f"*Date:* {postmortem.incident_started_at.strftime('%Y-%m-%d')}"
            )
        if postmortem.incident_duration_minutes:
            lines.append(f"*Duration:* {postmortem.incident_duration_minutes} minutes")
        lines.append("{info}")
        lines.append("")

        # Table of Contents
        lines.append("{toc}")
        lines.append("")

        # Executive Summary
        lines.append("h2. Executive Summary")
        lines.append("")
        lines.append(postmortem.executive_summary)
        lines.append("")

        # Timeline
        if postmortem.timeline:
            lines.append("h2. Timeline")
            lines.append("")
            lines.append("||Time||Event||Actor||")
            for event in postmortem.timeline:
                timestamp = event.timestamp.strftime("%Y-%m-%d %H:%M")
                actor = event.actor or "-"
                title = event.title.replace("|", "\\|")
                lines.append(f"|{timestamp}|{title}|{actor}|")
            lines.append("")

        # Root Cause
        if postmortem.root_cause:
            lines.append("h2. Root Cause Analysis")
            lines.append("")
            lines.append("{panel:title=Primary Cause|borderColor=#c0c0c0}")
            lines.append(postmortem.root_cause.primary_cause)
            lines.append("{panel}")
            lines.append("")

            if postmortem.root_cause.contributing_factors:
                lines.append("*Contributing Factors:*")
                for factor in postmortem.root_cause.contributing_factors:
                    lines.append(f"* {factor}")
                lines.append("")

            if postmortem.root_cause.trigger:
                lines.append(f"*Trigger:* {postmortem.root_cause.trigger}")
                lines.append("")

        # Impact
        if postmortem.impact:
            lines.append("h2. Impact Assessment")
            lines.append("")
            if postmortem.impact.summary:
                lines.append(postmortem.impact.summary)
                lines.append("")

            severity_color = {
                "critical": "red",
                "high": "orange",
                "medium": "yellow",
                "low": "green",
            }.get(postmortem.impact.severity.lower(), "grey")

            lines.append(
                f"{{status:colour={severity_color}|title={postmortem.impact.severity.upper()}}}"
            )
            lines.append("")

            if postmortem.impact.users_affected:
                lines.append(
                    f"* *Users Affected:* {postmortem.impact.users_affected:,}"
                )
            if postmortem.impact.services_affected:
                lines.append(
                    f"* *Services:* {', '.join(postmortem.impact.services_affected)}"
                )
            if postmortem.impact.sla_breach:
                lines.append("* *SLA Breach:* (/) Yes")
            if postmortem.impact.data_loss:
                lines.append("* *Data Loss:* (/) Yes")
            lines.append("")

        # Action Items
        if postmortem.action_items:
            lines.append("h2. Action Items")
            lines.append("")
            lines.append("||Priority||Item||Status||Owner||Due Date||")
            for item in postmortem.action_items:
                priority_icon = {
                    "critical": "(!) ",
                    "high": "(on) ",
                    "medium": "",
                    "low": "(i) ",
                }.get(item.priority.value, "")
                status_icon = {
                    "done": "(/)",
                    "in_progress": "(*)",
                    "todo": "(!)",
                    "wont_do": "(x)",
                }.get(item.status.value, "(!)")
                owner = item.owner or "TBD"
                due = item.due_date.strftime("%Y-%m-%d") if item.due_date else "-"
                lines.append(
                    f"|{priority_icon}{item.priority.value.upper()}|{item.title}|{status_icon}|{owner}|{due}|"
                )
            lines.append("")

        # Lessons Learned
        if (
            postmortem.lessons_learned
            or postmortem.what_went_well
            or postmortem.what_went_poorly
        ):
            lines.append("h2. Retrospective")
            lines.append("")

            if postmortem.lessons_learned:
                lines.append("h3. Lessons Learned")
                for lesson in postmortem.lessons_learned:
                    lines.append(f"* {lesson}")
                lines.append("")

            if postmortem.what_went_well:
                lines.append("h3. What Went Well")
                lines.append("{color:green}")
                for item in postmortem.what_went_well:
                    lines.append(f"* {item}")
                lines.append("{color}")
                lines.append("")

            if postmortem.what_went_poorly:
                lines.append("h3. What Went Poorly")
                lines.append("{color:red}")
                for item in postmortem.what_went_poorly:
                    lines.append(f"* {item}")
                lines.append("{color}")
                lines.append("")

        # Metadata
        lines.append("----")
        lines.append(f"_Postmortem ID: {postmortem.id}_")
        lines.append(f"_Incident ID: {postmortem.incident_id}_")
        if postmortem.ai_generated:
            lines.append(f"_AI Generated using {postmortem.ai_model}_")

        return "\n".join(lines)


class SlackTemplate(BaseTemplate):
    """Slack Block Kit JSON template."""

    format = PostmortemFormat.SLACK

    def render(self, postmortem: Postmortem) -> str:
        """Render postmortem as Slack Block Kit JSON."""
        blocks = []

        # Header
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📋 {postmortem.title}",
                    "emoji": True,
                },
            }
        )

        # Metadata section
        severity_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }.get(postmortem.severity.lower(), "⚪")

        status_text = postmortem.status.value.replace("_", " ").title()
        duration_text = (
            f"{postmortem.incident_duration_minutes} min"
            if postmortem.incident_duration_minutes
            else "Unknown"
        )

        blocks.append(
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Service:*\n{postmortem.service_name}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity_emoji} {postmortem.severity.upper()}",
                    },
                    {"type": "mrkdwn", "text": f"*Status:*\n{status_text}"},
                    {"type": "mrkdwn", "text": f"*Duration:*\n{duration_text}"},
                ],
            }
        )

        blocks.append({"type": "divider"})

        # Executive Summary
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Executive Summary*\n{postmortem.executive_summary[:2900]}",
                },
            }
        )

        # Root Cause
        if postmortem.root_cause:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*🔍 Root Cause*\n{postmortem.root_cause.primary_cause}",
                    },
                }
            )

            if postmortem.root_cause.contributing_factors:
                factors_text = "\n".join(
                    f"• {f}" for f in postmortem.root_cause.contributing_factors[:5]
                )
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Contributing Factors:*\n{factors_text}",
                        },
                    }
                )

        # Impact
        if postmortem.impact and postmortem.impact.summary:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📊 Impact*\n{postmortem.impact.summary}",
                    },
                }
            )

        # Timeline (condensed)
        if postmortem.timeline:
            blocks.append({"type": "divider"})
            timeline_items = postmortem.timeline[:5]
            timeline_text = "\n".join(
                f"• `{e.timestamp.strftime('%H:%M')}` {e.title}" for e in timeline_items
            )
            if len(postmortem.timeline) > 5:
                timeline_text += (
                    f"\n_...and {len(postmortem.timeline) - 5} more events_"
                )

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📅 Timeline*\n{timeline_text}",
                    },
                }
            )

        # Action Items (top 3)
        if postmortem.action_items:
            blocks.append({"type": "divider"})
            items_text = "\n".join(
                f"• [{item.priority.value.upper()}] {item.title}"
                for item in postmortem.action_items[:3]
            )
            if len(postmortem.action_items) > 3:
                items_text += (
                    f"\n_...and {len(postmortem.action_items) - 3} more items_"
                )

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*✅ Action Items*\n{items_text}",
                    },
                }
            )

        # Links
        link_elements = []
        if postmortem.alert_url:
            link_elements.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Alert"},
                    "url": postmortem.alert_url,
                }
            )
        if postmortem.dashboard_url:
            link_elements.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Dashboard"},
                    "url": postmortem.dashboard_url,
                }
            )

        if link_elements:
            blocks.append({"type": "divider"})
            blocks.append(
                {"type": "actions", "elements": link_elements[:5]}  # Slack limit
            )

        # Footer
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Postmortem ID: `{postmortem.id}` | "
                        f"Incident: `{postmortem.incident_id}` | "
                        f"{'🤖 AI Generated' if postmortem.ai_generated else '✍️ Manual'}",
                    }
                ],
            }
        )

        return json.dumps({"blocks": blocks}, indent=2)


class JSONTemplate(BaseTemplate):
    """Structured JSON export template."""

    format = PostmortemFormat.JSON

    def render(self, postmortem: Postmortem) -> str:
        """Render postmortem as structured JSON."""
        # Use Pydantic's built-in serialization with custom handling
        data = postmortem.model_dump(mode="json")

        # Ensure datetime fields are ISO formatted strings
        for key in [
            "created_at",
            "updated_at",
            "incident_started_at",
            "incident_resolved_at",
        ]:
            if data.get(key) and isinstance(data[key], str):
                # Already a string from model_dump
                pass
            elif data.get(key):
                data[key] = data[key].isoformat()

        # Format timeline timestamps
        for event in data.get("timeline", []):
            if isinstance(event.get("timestamp"), datetime):
                event["timestamp"] = event["timestamp"].isoformat()

        # Format action item due dates
        for item in data.get("action_items", []):
            if item.get("due_date") and isinstance(item["due_date"], datetime):
                item["due_date"] = item["due_date"].isoformat()

        # Format resolution step timestamps
        for step in data.get("resolution_steps", []):
            if step.get("timestamp") and isinstance(step["timestamp"], datetime):
                step["timestamp"] = step["timestamp"].isoformat()

        return json.dumps(data, indent=2, default=str)


# Template registry
TEMPLATES: dict[PostmortemFormat, BaseTemplate] = {
    PostmortemFormat.MARKDOWN: MarkdownTemplate(),
    PostmortemFormat.CONFLUENCE: ConfluenceTemplate(),
    PostmortemFormat.SLACK: SlackTemplate(),
    PostmortemFormat.JSON: JSONTemplate(),
}


def get_template(format: PostmortemFormat) -> BaseTemplate:
    """Get a template by format."""
    return TEMPLATES[format]


def render_postmortem(postmortem: Postmortem, format: PostmortemFormat) -> str:
    """Render a postmortem in the specified format."""
    template = get_template(format)
    return template.render(postmortem)
