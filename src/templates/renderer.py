"""Render templates into incident checklists."""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog

from .models import (
    IncidentTemplate,
    RenderedChecklist,
    RenderedStep,
    TemplateStepStatus,
)
from .store import template_store

logger = structlog.get_logger()


class TemplateRenderer:
    """Render incident templates into actionable checklists."""

    async def render(
        self,
        template: IncidentTemplate,
        incident_id: str,
        context: dict | None = None,
    ) -> RenderedChecklist:
        """
        Render a template into a checklist for a specific incident.
        
        Args:
            template: The template to render
            incident_id: ID of the incident this checklist is for
            context: Optional context for variable substitution
        
        Returns:
            RenderedChecklist ready for use
        """
        context = context or {}
        
        # Render each step
        rendered_steps: list[RenderedStep] = []
        
        for step in template.steps:
            # Apply variable substitution if needed
            title = self._substitute_variables(step.title, context)
            description = self._substitute_variables(step.description, context) if step.description else None
            suggested_action = self._substitute_variables(step.suggested_action, context) if step.suggested_action else None
            
            rendered_step = RenderedStep(
                step_id=step.id,
                order=step.order,
                title=title,
                description=description,
                suggested_action=suggested_action,
                time_estimate_minutes=step.time_estimate_minutes,
                runbook_url=step.runbook_url,
                is_critical=step.is_critical,
                status=TemplateStepStatus.PENDING,
                checked=False,
            )
            rendered_steps.append(rendered_step)
        
        # Sort by order
        rendered_steps.sort(key=lambda s: s.order)
        
        checklist = RenderedChecklist(
            id=f"chk-{uuid.uuid4().hex[:12]}",
            incident_id=incident_id,
            template_id=template.id,
            template_name=template.name,
            category=template.category,
            steps=rendered_steps,
        )
        
        # Increment template use count
        await template_store.increment_use_count(template.id)
        
        logger.info(
            "template_rendered",
            checklist_id=checklist.id,
            incident_id=incident_id,
            template_id=template.id,
            step_count=len(rendered_steps),
        )
        
        return checklist

    def _substitute_variables(self, text: str, context: dict) -> str:
        """Substitute {{variable}} placeholders with context values."""
        if not text:
            return text
        
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            text = text.replace(placeholder, str(value))
        
        return text

    async def render_to_markdown(
        self,
        checklist: RenderedChecklist,
        include_header: bool = True,
    ) -> str:
        """
        Render a checklist to Markdown format.
        
        Args:
            checklist: The checklist to render
            include_header: Whether to include a header section
        
        Returns:
            Markdown-formatted string
        """
        lines: list[str] = []
        
        if include_header:
            lines.append(f"# Incident Checklist: {checklist.template_name}")
            lines.append("")
            lines.append(f"**Category:** {checklist.category.value}")
            lines.append(f"**Incident ID:** {checklist.incident_id}")
            lines.append(f"**Progress:** {checklist.completed_steps}/{checklist.total_steps} steps ({checklist.progress_percent:.0f}%)")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        for step in checklist.steps:
            # Checkbox
            checkbox = "☑" if step.checked else "☐"
            critical = " 🔴" if step.is_critical else ""
            
            lines.append(f"### {checkbox} Step {step.order}: {step.title}{critical}")
            lines.append("")
            
            if step.description:
                lines.append(step.description)
                lines.append("")
            
            if step.suggested_action:
                lines.append(f"**Suggested Action:**")
                lines.append(f"```")
                lines.append(step.suggested_action)
                lines.append(f"```")
                lines.append("")
            
            if step.time_estimate_minutes:
                lines.append(f"⏱️ Estimated time: {step.time_estimate_minutes} minutes")
                lines.append("")
            
            if step.runbook_url:
                lines.append(f"📖 [Runbook]({step.runbook_url})")
                lines.append("")
            
            if step.status != TemplateStepStatus.PENDING:
                lines.append(f"**Status:** {step.status.value}")
                if step.completed_by:
                    lines.append(f"**Completed by:** {step.completed_by}")
                if step.completed_at:
                    lines.append(f"**Completed at:** {step.completed_at.isoformat()}")
                if step.notes:
                    lines.append(f"**Notes:** {step.notes}")
                lines.append("")
            
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)

    async def render_to_slack_blocks(
        self,
        checklist: RenderedChecklist,
    ) -> list[dict]:
        """
        Render a checklist to Slack Block Kit format.
        
        Returns:
            List of Slack block objects
        """
        blocks: list[dict] = []
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📋 {checklist.template_name}",
                "emoji": True,
            }
        })
        
        # Context
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Category:* {checklist.category.value} | *Progress:* {checklist.completed_steps}/{checklist.total_steps}"
                }
            ]
        })
        
        blocks.append({"type": "divider"})
        
        # Steps
        for step in checklist.steps:
            checkbox = "☑️" if step.checked else "⬜"
            critical = "🔴 " if step.is_critical else ""
            
            step_text = f"{checkbox} *{critical}Step {step.order}:* {step.title}"
            
            if step.description:
                step_text += f"\n{step.description}"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": step_text,
                }
            })
            
            # Action details
            details: list[str] = []
            if step.time_estimate_minutes:
                details.append(f"⏱️ {step.time_estimate_minutes}m")
            if step.runbook_url:
                details.append(f"<{step.runbook_url}|📖 Runbook>")
            
            if details:
                blocks.append({
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": " | ".join(details)}]
                })
            
            if step.suggested_action:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```{step.suggested_action}```"
                    }
                })
        
        return blocks

    async def render_to_html(
        self,
        checklist: RenderedChecklist,
    ) -> str:
        """
        Render a checklist to HTML format.
        
        Returns:
            HTML-formatted string
        """
        lines: list[str] = []
        
        lines.append(f"<div class='incident-checklist'>")
        lines.append(f"<h2>📋 {checklist.template_name}</h2>")
        lines.append(f"<p><strong>Category:</strong> {checklist.category.value}</p>")
        lines.append(f"<p><strong>Progress:</strong> {checklist.completed_steps}/{checklist.total_steps} ({checklist.progress_percent:.0f}%)</p>")
        
        # Progress bar
        lines.append(f"<div class='progress-bar'>")
        lines.append(f"<div class='progress' style='width: {checklist.progress_percent}%'></div>")
        lines.append(f"</div>")
        
        lines.append("<ol class='checklist-steps'>")
        
        for step in checklist.steps:
            checked = "checked" if step.checked else ""
            critical_class = "critical" if step.is_critical else ""
            
            lines.append(f"<li class='step {critical_class}'>")
            lines.append(f"<input type='checkbox' {checked} data-step-id='{step.step_id}'/>")
            lines.append(f"<span class='step-title'>{step.title}</span>")
            
            if step.is_critical:
                lines.append("<span class='critical-badge'>Critical</span>")
            
            if step.description:
                lines.append(f"<p class='step-description'>{step.description}</p>")
            
            if step.suggested_action:
                lines.append(f"<pre class='suggested-action'>{step.suggested_action}</pre>")
            
            if step.time_estimate_minutes:
                lines.append(f"<span class='time-estimate'>⏱️ {step.time_estimate_minutes}m</span>")
            
            if step.runbook_url:
                lines.append(f"<a href='{step.runbook_url}' class='runbook-link'>📖 Runbook</a>")
            
            lines.append("</li>")
        
        lines.append("</ol>")
        lines.append("</div>")
        
        return "\n".join(lines)

    async def update_step_status(
        self,
        checklist: RenderedChecklist,
        step_id: str,
        status: TemplateStepStatus,
        completed_by: str | None = None,
        notes: str | None = None,
    ) -> RenderedChecklist:
        """
        Update the status of a step in a checklist.
        
        Returns:
            Updated checklist
        """
        for step in checklist.steps:
            if step.step_id == step_id:
                step.status = status
                step.checked = status == TemplateStepStatus.COMPLETED
                
                if status == TemplateStepStatus.COMPLETED:
                    step.completed_at = datetime.utcnow()
                    step.completed_by = completed_by
                
                if notes:
                    step.notes = notes
                
                logger.info(
                    "step_status_updated",
                    checklist_id=checklist.id,
                    step_id=step_id,
                    status=status.value,
                )
                break
        
        checklist.updated_at = datetime.utcnow()
        return checklist


# Global renderer instance
template_renderer = TemplateRenderer()
