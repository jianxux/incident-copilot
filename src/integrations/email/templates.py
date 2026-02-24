"""Email template rendering."""

from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ...models import ContextCard
from .models import DigestData, EmailConfig, EmailTemplate, EmailTemplateType

logger = structlog.get_logger()

# Default template directory
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "web" / "templates" / "email"


class EmailTemplateRenderer:
    """Renders email templates from Jinja2 templates."""

    def __init__(self, templates_dir: Path | None = None):
        self.templates_dir = templates_dir or TEMPLATES_DIR

        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Add custom filters
        self.env.filters["format_datetime"] = self._format_datetime
        self.env.filters["format_duration"] = self._format_duration
        self.env.filters["severity_color"] = self._severity_color
        self.env.filters["severity_emoji"] = self._severity_emoji
        self.env.filters["truncate_text"] = self._truncate_text

    def render_context_card(
        self, card: ContextCard, config: EmailConfig
    ) -> tuple[str, str]:
        """Render context card email.

        Returns:
            Tuple of (html_body, text_body)
        """
        context = self._build_context_card_context(card, config)

        html_body = self._render_html("context_card.html", context)
        text_body = self._render_text_context_card(card, config)

        return html_body, text_body

    def render_digest(
        self, data: DigestData, config: EmailConfig, weekly: bool = False
    ) -> tuple[str, str]:
        """Render digest email.

        Returns:
            Tuple of (html_body, text_body)
        """
        template_name = "digest_weekly.html" if weekly else "digest_daily.html"
        context = self._build_digest_context(data, config, weekly)

        html_body = self._render_html(template_name, context)
        text_body = self._render_text_digest(data, config, weekly)

        return html_body, text_body

    def render_test(self, config: EmailConfig) -> tuple[str, str]:
        """Render test email.

        Returns:
            Tuple of (html_body, text_body)
        """
        context = {
            "config": config,
            "brand_color": config.brand_color,
            "logo_url": config.logo_url,
            "footer": config.custom_footer,
            "timestamp": datetime.now(UTC),
        }

        html_body = self._render_html("test.html", context)
        text_body = self._render_text_test(config)

        return html_body, text_body

    def render_custom(
        self, template: EmailTemplate, variables: dict[str, Any], config: EmailConfig
    ) -> tuple[str, str]:
        """Render a custom template.

        Returns:
            Tuple of (html_body, text_body)
        """
        context = {
            **variables,
            "config": config,
            "brand_color": config.brand_color,
            "logo_url": config.logo_url,
            "footer": config.custom_footer,
        }

        # Render from template strings
        html_template = self.env.from_string(template.html_template)
        text_template = self.env.from_string(template.text_template)

        html_body = html_template.render(**context)
        text_body = text_template.render(**context)

        return html_body, text_body

    def get_subject(
        self,
        template_type: EmailTemplateType,
        card: ContextCard | None = None,
        data: DigestData | None = None,
    ) -> str:
        """Get email subject for a template type."""
        if template_type == EmailTemplateType.CONTEXT_CARD and card:
            severity_prefix = {
                "critical": "🔴 CRITICAL",
                "high": "🟠 HIGH",
                "medium": "🟡 MEDIUM",
                "low": "🟢 LOW",
                "info": "🔵 INFO",
            }
            prefix = severity_prefix.get(card.severity.value, "⚪")
            return f"{prefix}: {card.service_name} - {card.title[:50]}"

        elif template_type == EmailTemplateType.DIGEST_DAILY and data:
            return f"📊 Daily Incident Report - {data.period_end.strftime('%Y-%m-%d')}"

        elif template_type == EmailTemplateType.DIGEST_WEEKLY and data:
            return f"📊 Weekly Incident Report - Week of {data.period_start.strftime('%Y-%m-%d')}"

        elif template_type == EmailTemplateType.TEST:
            return "🧪 Incident Copilot - Test Email"

        return "Incident Copilot Notification"

    def list_templates(self) -> list[dict[str, Any]]:
        """List available templates."""
        templates = []

        for template_file in self.templates_dir.glob("*.html"):
            template_name = template_file.stem
            templates.append(
                {
                    "id": template_name,
                    "name": template_name.replace("_", " ").title(),
                    "type": self._infer_template_type(template_name),
                    "file": template_file.name,
                }
            )

        return templates

    def _render_html(self, template_name: str, context: dict[str, Any]) -> str:
        """Render HTML template."""
        try:
            template = self.env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            logger.error("template_render_error", template=template_name, error=str(e))
            # Return a basic fallback
            return self._fallback_html(context)

    def _build_context_card_context(
        self, card: ContextCard, config: EmailConfig
    ) -> dict[str, Any]:
        """Build template context for context card."""
        return {
            "card": card,
            "config": config,
            "brand_color": config.brand_color,
            "logo_url": config.logo_url,
            "footer": config.custom_footer,
            "severity_color": self._severity_color(card.severity.value),
            "severity_emoji": self._severity_emoji(card.severity.value),
            "triggered_at_formatted": card.triggered_at.strftime("%Y-%m-%d %H:%M UTC"),
            "has_github": card.github is not None and bool(card.github.recent_deploys),
            "has_gitlab": card.gitlab is not None and bool(card.gitlab.recent_deploys),
            "has_ai_summary": card.ai_summary is not None,
            "has_similar_incidents": bool(card.similar_incidents),
            "has_runbooks": bool(card.runbooks),
            "has_oncall": card.oncall is not None and card.oncall.has_oncall,
        }

    def _build_digest_context(
        self, data: DigestData, config: EmailConfig, weekly: bool
    ) -> dict[str, Any]:
        """Build template context for digest."""
        return {
            "data": data,
            "config": config,
            "brand_color": config.brand_color,
            "logo_url": config.logo_url,
            "footer": config.custom_footer,
            "period_type": "Week" if weekly else "Day",
            "period_start": data.period_start.strftime("%Y-%m-%d"),
            "period_end": data.period_end.strftime("%Y-%m-%d"),
            "mttr_formatted": (
                self._format_duration(data.mttr_minutes) if data.mttr_minutes else "N/A"
            ),
        }

    def _render_text_context_card(self, card: ContextCard, config: EmailConfig) -> str:
        """Render plain text version of context card."""
        lines = [
            f"{'=' * 60}",
            f"INCIDENT ALERT: {card.title}",
            f"{'=' * 60}",
            "",
            f"Severity: {card.severity.value.upper()}",
            f"Service: {card.service_name}",
            f"Triggered: {card.triggered_at.strftime('%Y-%m-%d %H:%M UTC')}",
            "",
        ]

        if card.alert_url:
            lines.append(f"Alert URL: {card.alert_url}")
            lines.append("")

        # Recent deployments
        if card.github and card.github.recent_deploys:
            lines.append("RECENT DEPLOYMENTS:")
            lines.append("-" * 40)
            for deploy in card.github.recent_deploys[:3]:
                lines.append(f"  - {deploy.short_sha} by {deploy.author}")
                lines.append(f"    {deploy.message[:60]}")
                if deploy.url:
                    lines.append(f"    {deploy.url}")
            lines.append("")

        # AI Summary
        if card.ai_summary:
            lines.append("AI ANALYSIS:")
            lines.append("-" * 40)
            for issue in card.ai_summary.top_issues[:5]:
                lines.append(f"  • {issue}")
            if card.ai_summary.explanation:
                lines.append(f"\n  {card.ai_summary.explanation[:200]}")
            lines.append("")

        # Similar incidents
        if card.similar_incidents:
            lines.append("SIMILAR PAST INCIDENTS:")
            lines.append("-" * 40)
            for inc in card.similar_incidents[:3]:
                lines.append(
                    f"  • {inc.title[:50]} ({inc.occurred_at.strftime('%Y-%m-%d')})"
                )
                if inc.resolution:
                    lines.append(f"    Resolution: {inc.resolution[:80]}")
            lines.append("")

        # On-call
        if card.oncall and card.oncall.has_oncall:
            lines.append("ON-CALL:")
            lines.append("-" * 40)
            for person in card.oncall.oncall_persons[:3]:
                lines.append(f"  • {person.name} ({person.email})")
            lines.append("")

        # Links
        if card.runbook_url or card.dashboard_url:
            lines.append("QUICK LINKS:")
            lines.append("-" * 40)
            if card.runbook_url:
                lines.append(f"  Runbook: {card.runbook_url}")
            if card.dashboard_url:
                lines.append(f"  Dashboard: {card.dashboard_url}")
            lines.append("")

        # Footer
        if config.custom_footer:
            lines.append("-" * 60)
            lines.append(config.custom_footer)

        return "\n".join(lines)

    def _render_text_digest(
        self, data: DigestData, config: EmailConfig, weekly: bool
    ) -> str:
        """Render plain text version of digest."""
        period = "Weekly" if weekly else "Daily"
        lines = [
            f"{'=' * 60}",
            f"{period.upper()} INCIDENT REPORT",
            f"Period: {data.period_start.strftime('%Y-%m-%d')} to {data.period_end.strftime('%Y-%m-%d')}",
            f"{'=' * 60}",
            "",
            "SUMMARY:",
            "-" * 40,
            f"  Total Incidents: {data.total_incidents}",
            f"  Critical: {data.critical_count}",
            f"  High: {data.high_count}",
            f"  Medium: {data.medium_count}",
            f"  Low: {data.low_count}",
            "",
        ]

        if data.mttr_minutes:
            lines.append(
                f"  Mean Time to Resolve: {self._format_duration(data.mttr_minutes)}"
            )
            lines.append("")

        if data.services_affected:
            lines.append("SERVICES AFFECTED:")
            lines.append("-" * 40)
            for service in data.services_affected[:10]:
                lines.append(f"  • {service}")
            lines.append("")

        if data.incidents:
            lines.append("INCIDENTS:")
            lines.append("-" * 40)
            for inc in data.incidents[:20]:
                status_icon = "✓" if inc.status == "resolved" else "○"
                lines.append(
                    f"  {status_icon} [{inc.severity.upper()}] {inc.title[:50]}"
                )
                lines.append(
                    f"    Service: {inc.service_name} | {inc.triggered_at.strftime('%m/%d %H:%M')}"
                )
            lines.append("")

        # Footer
        if config.custom_footer:
            lines.append("-" * 60)
            lines.append(config.custom_footer)

        return "\n".join(lines)

    def _render_text_test(self, config: EmailConfig) -> str:
        """Render plain text version of test email."""
        lines = [
            "=" * 60,
            "INCIDENT COPILOT - TEST EMAIL",
            "=" * 60,
            "",
            "This is a test email from Incident Copilot.",
            "",
            "Your email configuration is working correctly!",
            "",
            f"Provider: {config.provider.value.upper()}",
            f"From: {config.from_name} <{config.from_email}>",
            f"Timestamp: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
        ]

        if config.custom_footer:
            lines.append("-" * 60)
            lines.append(config.custom_footer)

        return "\n".join(lines)

    def _fallback_html(self, context: dict[str, Any]) -> str:
        """Generate fallback HTML when template fails."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Incident Notification</title></head>
        <body style="font-family: sans-serif; padding: 20px;">
            <h1>Incident Notification</h1>
            <p>Template rendering failed. Please check your email templates.</p>
            <p>Context keys: {", ".join(context.keys())}</p>
        </body>
        </html>
        """

    def _infer_template_type(self, template_name: str) -> str:
        """Infer template type from name."""
        if "context_card" in template_name:
            return EmailTemplateType.CONTEXT_CARD.value
        elif "digest_daily" in template_name:
            return EmailTemplateType.DIGEST_DAILY.value
        elif "digest_weekly" in template_name:
            return EmailTemplateType.DIGEST_WEEKLY.value
        elif "test" in template_name:
            return EmailTemplateType.TEST.value
        return EmailTemplateType.CUSTOM.value

    @staticmethod
    def _format_datetime(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M UTC") -> str:
        """Format datetime for display."""
        if dt is None:
            return "N/A"
        return dt.strftime(fmt)

    @staticmethod
    def _format_duration(minutes: float | None) -> str:
        """Format duration in minutes to human readable."""
        if minutes is None:
            return "N/A"
        if minutes < 60:
            return f"{int(minutes)}m"
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        if hours < 24:
            return f"{hours}h {mins}m"
        days = hours // 24
        hours = hours % 24
        return f"{days}d {hours}h"

    @staticmethod
    def _severity_color(severity: str) -> str:
        """Get color for severity level."""
        colors = {
            "critical": "#dc2626",  # red-600
            "high": "#ea580c",  # orange-600
            "medium": "#ca8a04",  # yellow-600
            "low": "#16a34a",  # green-600
            "info": "#2563eb",  # blue-600
        }
        return colors.get(severity.lower(), "#6b7280")  # gray-500

    @staticmethod
    def _severity_emoji(severity: str) -> str:
        """Get emoji for severity level."""
        emojis = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "🔵",
        }
        return emojis.get(severity.lower(), "⚪")

    @staticmethod
    def _truncate_text(text: str, length: int = 100) -> str:
        """Truncate text to specified length."""
        if len(text) <= length:
            return text
        return text[: length - 3] + "..."
