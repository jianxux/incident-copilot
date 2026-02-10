"""Report templates for HTML and Markdown output."""

from datetime import datetime
from typing import Any

from jinja2 import BaseLoader, Environment


class ReportTemplates:
    """
    Templates for rendering reports in HTML and Markdown formats.

    Uses Jinja2 for template rendering with custom filters.
    """

    def __init__(self):
        self.env = Environment(loader=BaseLoader(), autoescape=True)
        self._register_filters()

    def _register_filters(self) -> None:
        """Register custom Jinja2 filters."""
        self.env.filters["format_date"] = self._format_date
        self.env.filters["format_datetime"] = self._format_datetime
        self.env.filters["format_duration"] = self._format_duration
        self.env.filters["format_percent"] = self._format_percent
        self.env.filters["severity_color"] = self._severity_color
        self.env.filters["severity_emoji"] = self._severity_emoji
        self.env.filters["trend_arrow"] = self._trend_arrow

    @staticmethod
    def _format_date(value: datetime | None) -> str:
        if not value:
            return "N/A"
        return value.strftime("%Y-%m-%d")

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if not value:
            return "N/A"
        return value.strftime("%Y-%m-%d %H:%M UTC")

    @staticmethod
    def _format_duration(minutes: float | None) -> str:
        if minutes is None:
            return "N/A"
        if minutes < 1:
            return f"{int(minutes * 60)}s"
        if minutes < 60:
            return f"{int(minutes)}m"
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours}h {mins}m" if mins else f"{hours}h"

    @staticmethod
    def _format_percent(value: float | None) -> str:
        if value is None:
            return "N/A"
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.1f}%"

    @staticmethod
    def _severity_color(severity: str) -> str:
        colors = {
            "critical": "#dc3545",
            "high": "#fd7e14",
            "medium": "#ffc107",
            "low": "#28a745",
            "info": "#17a2b8",
        }
        return colors.get(severity.lower(), "#6c757d")

    @staticmethod
    def _severity_emoji(severity: str) -> str:
        emojis = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "🔵",
        }
        return emojis.get(severity.lower(), "⚪")

    @staticmethod
    def _trend_arrow(trend: str) -> str:
        arrows = {
            "improving": "📈",
            "degrading": "📉",
            "stable": "➡️",
        }
        return arrows.get(trend.lower(), "➡️")

    def render_html(self, template_name: str, context: dict[str, Any]) -> str:
        """Render an HTML template."""
        template_str = self._get_html_template(template_name)
        template = self.env.from_string(template_str)
        return template.render(**context)

    def render_markdown(self, template_name: str, context: dict[str, Any]) -> str:
        """Render a Markdown template."""
        template_str = self._get_markdown_template(template_name)
        template = self.env.from_string(template_str)
        return template.render(**context)

    def _get_html_template(self, name: str) -> str:
        """Get HTML template by name."""
        templates = {
            "daily_summary": self.HTML_DAILY_SUMMARY,
            "weekly_reliability": self.HTML_WEEKLY_RELIABILITY,
            "monthly_analysis": self.HTML_MONTHLY_ANALYSIS,
            "incident_summary": self.HTML_INCIDENT_SUMMARY,
            "sla_report": self.HTML_SLA_REPORT,
        }
        return templates.get(name, self.HTML_DAILY_SUMMARY)

    def _get_markdown_template(self, name: str) -> str:
        """Get Markdown template by name."""
        templates = {
            "daily_summary": self.MD_DAILY_SUMMARY,
            "weekly_reliability": self.MD_WEEKLY_RELIABILITY,
            "monthly_analysis": self.MD_MONTHLY_ANALYSIS,
            "incident_summary": self.MD_INCIDENT_SUMMARY,
            "sla_report": self.MD_SLA_REPORT,
        }
        return templates.get(name, self.MD_DAILY_SUMMARY)

    # =========================================================================
    # HTML Templates
    # =========================================================================

    HTML_BASE_STYLE = """
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background-color: #fff;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 30px;
        }
        .header {
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #2c3e50;
            margin: 0 0 10px 0;
            font-size: 28px;
        }
        .header .subtitle {
            color: #6c757d;
            font-size: 14px;
        }
        .logo {
            max-height: 50px;
            margin-bottom: 15px;
        }
        .section {
            margin-bottom: 30px;
        }
        .section h2 {
            color: #2c3e50;
            font-size: 20px;
            border-bottom: 1px solid #e9ecef;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .metric-card {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
        }
        .metric-card .value {
            font-size: 32px;
            font-weight: bold;
            color: #2c3e50;
        }
        .metric-card .label {
            font-size: 12px;
            color: #6c757d;
            text-transform: uppercase;
        }
        .metric-card .change {
            font-size: 12px;
            margin-top: 5px;
        }
        .change.positive { color: #28a745; }
        .change.negative { color: #dc3545; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e9ecef;
        }
        th {
            background-color: #f8f9fa;
            font-weight: 600;
            color: #495057;
            font-size: 12px;
            text-transform: uppercase;
        }
        .severity-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            color: white;
        }
        .severity-critical { background-color: #dc3545; }
        .severity-high { background-color: #fd7e14; }
        .severity-medium { background-color: #ffc107; color: #333; }
        .severity-low { background-color: #28a745; }
        .severity-info { background-color: #17a2b8; }
        .insight-card {
            background: #e7f3ff;
            border-left: 4px solid #007bff;
            padding: 15px;
            margin: 10px 0;
            border-radius: 0 8px 8px 0;
        }
        .recommendation-card {
            background: #e8f5e9;
            border-left: 4px solid #28a745;
            padding: 15px;
            margin: 10px 0;
            border-radius: 0 8px 8px 0;
        }
        .footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e9ecef;
            text-align: center;
            color: #6c757d;
            font-size: 12px;
        }
        .trend-improving { color: #28a745; }
        .trend-degrading { color: #dc3545; }
        .trend-stable { color: #6c757d; }
    </style>
    """

    HTML_DAILY_SUMMARY = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    {{ style }}
</head>
<body>
    <div class="container">
        <div class="header">
            {% if logo_url %}<img src="{{ logo_url }}" class="logo" alt="Logo">{% endif %}
            <h1>{{ title }}</h1>
            <div class="subtitle">{{ subtitle | default('Daily Incident Summary') }}</div>
            <div class="subtitle">{{ period_start | format_date }} - {{ period_end | format_date }}</div>
        </div>

        {% if executive_summary %}
        <div class="section">
            <h2>📋 Executive Summary</h2>
            <p>{{ executive_summary }}</p>
        </div>
        {% endif %}

        {% if metrics %}
        <div class="section">
            <h2>📊 Key Metrics</h2>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="value">{{ metrics.total_incidents }}</div>
                    <div class="label">Total Incidents</div>
                    {% if metrics.incident_count_change_percent is not none %}
                    <div class="change {% if metrics.incident_count_change_percent > 0 %}negative{% else %}positive{% endif %}">
                        {{ metrics.incident_count_change_percent | format_percent }} vs prev period
                    </div>
                    {% endif %}
                </div>
                <div class="metric-card">
                    <div class="value">{{ metrics.mean_mttr_minutes | format_duration }}</div>
                    <div class="label">Mean MTTR</div>
                    {% if metrics.mttr_change_percent is not none %}
                    <div class="change {% if metrics.mttr_change_percent > 0 %}negative{% else %}positive{% endif %}">
                        {{ metrics.mttr_change_percent | format_percent }} vs prev period
                    </div>
                    {% endif %}
                </div>
                {% if metrics.mean_tta_minutes %}
                <div class="metric-card">
                    <div class="value">{{ metrics.mean_tta_minutes | format_duration }}</div>
                    <div class="label">Mean TTA</div>
                </div>
                {% endif %}
                <div class="metric-card">
                    <div class="value">
                        <span class="trend-{{ metrics.trend }}">{{ metrics.trend | trend_arrow }}</span>
                    </div>
                    <div class="label">Trend</div>
                </div>
            </div>

            {% if metrics.incidents_by_severity %}
            <h3>By Severity</h3>
            <table>
                <tr>
                    {% for sev, count in metrics.incidents_by_severity.items() %}
                    <th>{{ sev | upper }}</th>
                    {% endfor %}
                </tr>
                <tr>
                    {% for sev, count in metrics.incidents_by_severity.items() %}
                    <td><span class="severity-badge severity-{{ sev }}">{{ count }}</span></td>
                    {% endfor %}
                </tr>
            </table>
            {% endif %}
        </div>
        {% endif %}

        {% if incidents %}
        <div class="section">
            <h2>🚨 Incidents</h2>
            <table>
                <thead>
                    <tr>
                        <th>Severity</th>
                        <th>Service</th>
                        <th>Title</th>
                        <th>Duration</th>
                        <th>Time</th>
                    </tr>
                </thead>
                <tbody>
                    {% for incident in incidents %}
                    <tr>
                        <td><span class="severity-badge severity-{{ incident.severity }}">{{ incident.severity }}</span></td>
                        <td>{{ incident.service_name }}</td>
                        <td>{{ incident.title[:60] }}{% if incident.title|length > 60 %}...{% endif %}</td>
                        <td>{{ incident.duration_minutes | format_duration }}</td>
                        <td>{{ incident.triggered_at | format_datetime }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}

        {% if ai_insights %}
        <div class="section">
            <h2>💡 AI Insights</h2>
            {% for insight in ai_insights %}
            <div class="insight-card">{{ insight }}</div>
            {% endfor %}
        </div>
        {% endif %}

        {% if ai_recommendations %}
        <div class="section">
            <h2>✅ Recommendations</h2>
            {% for rec in ai_recommendations %}
            <div class="recommendation-card">{{ rec }}</div>
            {% endfor %}
        </div>
        {% endif %}

        <div class="footer">
            {% if footer %}{{ footer }}{% else %}
            Generated by Incident Copilot at {{ generated_at | format_datetime }}
            {% endif %}
        </div>
    </div>
</body>
</html>"""

    HTML_WEEKLY_RELIABILITY = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    {{ style }}
</head>
<body>
    <div class="container">
        <div class="header">
            {% if logo_url %}<img src="{{ logo_url }}" class="logo" alt="Logo">{% endif %}
            <h1>{{ title }}</h1>
            <div class="subtitle">Weekly Reliability Report</div>
            <div class="subtitle">{{ period_start | format_date }} - {{ period_end | format_date }}</div>
        </div>

        {% if executive_summary %}
        <div class="section">
            <h2>📋 Executive Summary</h2>
            <p>{{ executive_summary }}</p>
        </div>
        {% endif %}

        {% if metrics %}
        <div class="section">
            <h2>📊 Weekly Metrics</h2>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="value">{{ metrics.total_incidents }}</div>
                    <div class="label">Total Incidents</div>
                    {% if metrics.incident_count_change_percent is not none %}
                    <div class="change {% if metrics.incident_count_change_percent > 0 %}negative{% else %}positive{% endif %}">
                        {{ metrics.incident_count_change_percent | format_percent }} WoW
                    </div>
                    {% endif %}
                </div>
                <div class="metric-card">
                    <div class="value">{{ metrics.mean_mttr_minutes | format_duration }}</div>
                    <div class="label">Mean MTTR</div>
                </div>
                <div class="metric-card">
                    <div class="value">{{ metrics.p90_mttr_minutes | format_duration }}</div>
                    <div class="label">P90 MTTR</div>
                </div>
                <div class="metric-card">
                    <div class="value" style="color: {{ metrics.trend | severity_color }}">
                        {{ metrics.trend | trend_arrow }} {{ metrics.trend | title }}
                    </div>
                    <div class="label">Weekly Trend</div>
                </div>
            </div>

            {% if metrics.incidents_by_service %}
            <h3>Incidents by Service</h3>
            <table>
                <thead>
                    <tr>
                        <th>Service</th>
                        <th>Incidents</th>
                    </tr>
                </thead>
                <tbody>
                    {% for service, count in metrics.incidents_by_service.items() %}
                    <tr>
                        <td>{{ service }}</td>
                        <td>{{ count }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% endif %}
        </div>
        {% endif %}

        {% if trends %}
        <div class="section">
            <h2>📈 Trends</h2>
            {% for trend_name, trend_data in trends.items() %}
            <div class="insight-card">
                <strong>{{ trend_name | replace('_', ' ') | title }}:</strong> {{ trend_data }}
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if incidents %}
        <div class="section">
            <h2>🚨 Top Incidents This Week</h2>
            <table>
                <thead>
                    <tr>
                        <th>Severity</th>
                        <th>Service</th>
                        <th>Title</th>
                        <th>MTTR</th>
                        <th>Root Cause</th>
                    </tr>
                </thead>
                <tbody>
                    {% for incident in incidents[:10] %}
                    <tr>
                        <td><span class="severity-badge severity-{{ incident.severity }}">{{ incident.severity }}</span></td>
                        <td>{{ incident.service_name }}</td>
                        <td>{{ incident.title[:50] }}{% if incident.title|length > 50 %}...{% endif %}</td>
                        <td>{{ incident.duration_minutes | format_duration }}</td>
                        <td>{{ incident.root_cause[:40] if incident.root_cause else 'TBD' }}{% if incident.root_cause and incident.root_cause|length > 40 %}...{% endif %}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}

        {% if ai_insights %}
        <div class="section">
            <h2>💡 Weekly Insights</h2>
            {% for insight in ai_insights %}
            <div class="insight-card">{{ insight }}</div>
            {% endfor %}
        </div>
        {% endif %}

        {% if ai_recommendations %}
        <div class="section">
            <h2>✅ Action Items</h2>
            {% for rec in ai_recommendations %}
            <div class="recommendation-card">{{ rec }}</div>
            {% endfor %}
        </div>
        {% endif %}

        <div class="footer">
            {% if footer %}{{ footer }}{% else %}
            Generated by Incident Copilot at {{ generated_at | format_datetime }}
            {% endif %}
        </div>
    </div>
</body>
</html>"""

    HTML_MONTHLY_ANALYSIS = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    {{ style }}
</head>
<body>
    <div class="container">
        <div class="header">
            {% if logo_url %}<img src="{{ logo_url }}" class="logo" alt="Logo">{% endif %}
            <h1>{{ title }}</h1>
            <div class="subtitle">Monthly Reliability Analysis</div>
            <div class="subtitle">{{ period_start | format_date }} - {{ period_end | format_date }}</div>
        </div>

        {% if executive_summary %}
        <div class="section">
            <h2>📋 Executive Summary</h2>
            <p>{{ executive_summary }}</p>
        </div>
        {% endif %}

        {% if metrics %}
        <div class="section">
            <h2>📊 Monthly Overview</h2>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="value">{{ metrics.total_incidents }}</div>
                    <div class="label">Total Incidents</div>
                    {% if metrics.incident_count_change_percent is not none %}
                    <div class="change {% if metrics.incident_count_change_percent > 0 %}negative{% else %}positive{% endif %}">
                        {{ metrics.incident_count_change_percent | format_percent }} MoM
                    </div>
                    {% endif %}
                </div>
                <div class="metric-card">
                    <div class="value">{{ metrics.mean_mttr_minutes | format_duration }}</div>
                    <div class="label">Mean MTTR</div>
                    {% if metrics.mttr_change_percent is not none %}
                    <div class="change {% if metrics.mttr_change_percent > 0 %}negative{% else %}positive{% endif %}">
                        {{ metrics.mttr_change_percent | format_percent }} MoM
                    </div>
                    {% endif %}
                </div>
                <div class="metric-card">
                    <div class="value">{{ metrics.median_mttr_minutes | format_duration }}</div>
                    <div class="label">Median MTTR</div>
                </div>
                <div class="metric-card">
                    <div class="value">{{ metrics.p90_mttr_minutes | format_duration }}</div>
                    <div class="label">P90 MTTR</div>
                </div>
            </div>
        </div>
        {% endif %}

        {% if trends %}
        <div class="section">
            <h2>📈 Monthly Trends</h2>
            {% for trend_name, trend_data in trends.items() %}
            <div class="insight-card">
                <strong>{{ trend_name | replace('_', ' ') | title }}:</strong> {{ trend_data }}
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if ai_insights %}
        <div class="section">
            <h2>💡 AI Analysis</h2>
            {% for insight in ai_insights %}
            <div class="insight-card">{{ insight }}</div>
            {% endfor %}
        </div>
        {% endif %}

        {% if ai_recommendations %}
        <div class="section">
            <h2>✅ Strategic Recommendations</h2>
            {% for rec in ai_recommendations %}
            <div class="recommendation-card">{{ rec }}</div>
            {% endfor %}
        </div>
        {% endif %}

        <div class="footer">
            {% if footer %}{{ footer }}{% else %}
            Generated by Incident Copilot at {{ generated_at | format_datetime }}
            {% endif %}
        </div>
    </div>
</body>
</html>"""

    HTML_INCIDENT_SUMMARY = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    {{ style }}
</head>
<body>
    <div class="container">
        <div class="header">
            {% if logo_url %}<img src="{{ logo_url }}" class="logo" alt="Logo">{% endif %}
            <h1>{{ title }}</h1>
            <div class="subtitle">Incident Summary Report</div>
        </div>

        {% if incidents %}
        <div class="section">
            <h2>🚨 Incidents ({{ incidents | length }})</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Severity</th>
                        <th>Service</th>
                        <th>Title</th>
                        <th>Duration</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for incident in incidents %}
                    <tr>
                        <td><code>{{ incident.incident_id[:8] }}</code></td>
                        <td><span class="severity-badge severity-{{ incident.severity }}">{{ incident.severity }}</span></td>
                        <td>{{ incident.service_name }}</td>
                        <td>{{ incident.title[:50] }}{% if incident.title|length > 50 %}...{% endif %}</td>
                        <td>{{ incident.duration_minutes | format_duration }}</td>
                        <td>{{ 'Resolved' if incident.resolved_at else 'Active' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}

        <div class="footer">
            {% if footer %}{{ footer }}{% else %}
            Generated by Incident Copilot at {{ generated_at | format_datetime }}
            {% endif %}
        </div>
    </div>
</body>
</html>"""

    HTML_SLA_REPORT = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    {{ style }}
    <style>
        .sla-status-met { color: #28a745; font-weight: bold; }
        .sla-status-breached { color: #dc3545; font-weight: bold; }
        .progress-bar {
            background: #e9ecef;
            border-radius: 4px;
            height: 20px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }
        .progress-fill.good { background: #28a745; }
        .progress-fill.warning { background: #ffc107; }
        .progress-fill.danger { background: #dc3545; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            {% if logo_url %}<img src="{{ logo_url }}" class="logo" alt="Logo">{% endif %}
            <h1>{{ title }}</h1>
            <div class="subtitle">SLA Compliance Report</div>
            <div class="subtitle">{{ period_start | format_date }} - {{ period_end | format_date }}</div>
        </div>

        {% if metrics %}
        <div class="section">
            <h2>📊 SLA Overview</h2>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="value">{{ metrics.total_incidents }}</div>
                    <div class="label">Total Incidents</div>
                </div>
                <div class="metric-card">
                    <div class="value">{{ sla_met_count | default(0) }}</div>
                    <div class="label">SLA Met</div>
                </div>
                <div class="metric-card">
                    <div class="value">{{ sla_breached_count | default(0) }}</div>
                    <div class="label">SLA Breached</div>
                </div>
                <div class="metric-card">
                    <div class="value">{{ sla_compliance_percent | default('N/A') }}%</div>
                    <div class="label">Compliance Rate</div>
                </div>
            </div>
        </div>
        {% endif %}

        {% if sla_by_severity %}
        <div class="section">
            <h2>📈 SLA by Severity</h2>
            <table>
                <thead>
                    <tr>
                        <th>Severity</th>
                        <th>Target MTTR</th>
                        <th>Actual MTTR</th>
                        <th>Compliance</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for sla in sla_by_severity %}
                    <tr>
                        <td><span class="severity-badge severity-{{ sla.severity }}">{{ sla.severity }}</span></td>
                        <td>{{ sla.target_mttr | format_duration }}</td>
                        <td>{{ sla.actual_mttr | format_duration }}</td>
                        <td>
                            <div class="progress-bar">
                                <div class="progress-fill {% if sla.compliance >= 95 %}good{% elif sla.compliance >= 80 %}warning{% else %}danger{% endif %}"
                                     style="width: {{ sla.compliance }}%"></div>
                            </div>
                            {{ sla.compliance }}%
                        </td>
                        <td class="sla-status-{% if sla.met %}met{% else %}breached{% endif %}">
                            {{ 'MET' if sla.met else 'BREACHED' }}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}

        {% if breached_incidents %}
        <div class="section">
            <h2>⚠️ SLA Breached Incidents</h2>
            <table>
                <thead>
                    <tr>
                        <th>Severity</th>
                        <th>Service</th>
                        <th>Title</th>
                        <th>Target</th>
                        <th>Actual</th>
                        <th>Breach</th>
                    </tr>
                </thead>
                <tbody>
                    {% for incident in breached_incidents %}
                    <tr>
                        <td><span class="severity-badge severity-{{ incident.severity }}">{{ incident.severity }}</span></td>
                        <td>{{ incident.service_name }}</td>
                        <td>{{ incident.title[:40] }}...</td>
                        <td>{{ incident.target_mttr | format_duration }}</td>
                        <td>{{ incident.actual_mttr | format_duration }}</td>
                        <td class="sla-status-breached">+{{ incident.breach_amount | format_duration }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}

        <div class="footer">
            {% if footer %}{{ footer }}{% else %}
            Generated by Incident Copilot at {{ generated_at | format_datetime }}
            {% endif %}
        </div>
    </div>
</body>
</html>"""

    # =========================================================================
    # Markdown Templates
    # =========================================================================

    MD_DAILY_SUMMARY = """# {{ title }}

{{ subtitle | default('Daily Incident Summary') }}

**Period:** {{ period_start | format_date }} - {{ period_end | format_date }}

---

{% if executive_summary %}
## 📋 Executive Summary

{{ executive_summary }}

{% endif %}
{% if metrics %}
## 📊 Key Metrics

| Metric | Value | Change |
|--------|-------|--------|
| Total Incidents | {{ metrics.total_incidents }} | {{ metrics.incident_count_change_percent | format_percent if metrics.incident_count_change_percent is not none else 'N/A' }} |
| Mean MTTR | {{ metrics.mean_mttr_minutes | format_duration }} | {{ metrics.mttr_change_percent | format_percent if metrics.mttr_change_percent is not none else 'N/A' }} |
{% if metrics.mean_tta_minutes %}| Mean TTA | {{ metrics.mean_tta_minutes | format_duration }} | - |{% endif %}
| Trend | {{ metrics.trend | trend_arrow }} {{ metrics.trend | title }} | - |

{% if metrics.incidents_by_severity %}
### By Severity
{% for sev, count in metrics.incidents_by_severity.items() %}
- {{ sev | severity_emoji }} **{{ sev | upper }}**: {{ count }}
{% endfor %}
{% endif %}

{% endif %}
{% if incidents %}
## 🚨 Incidents

| Severity | Service | Title | Duration | Time |
|----------|---------|-------|----------|------|
{% for incident in incidents %}
| {{ incident.severity | severity_emoji }} {{ incident.severity }} | {{ incident.service_name }} | {{ incident.title[:40] }}{% if incident.title|length > 40 %}...{% endif %} | {{ incident.duration_minutes | format_duration }} | {{ incident.triggered_at | format_datetime }} |
{% endfor %}

{% endif %}
{% if ai_insights %}
## 💡 AI Insights

{% for insight in ai_insights %}
> {{ insight }}

{% endfor %}
{% endif %}

{% if ai_recommendations %}
## ✅ Recommendations

{% for rec in ai_recommendations %}
- [ ] {{ rec }}
{% endfor %}
{% endif %}

---

{% if footer %}{{ footer }}{% else %}*Generated by Incident Copilot at {{ generated_at | format_datetime }}*{% endif %}
"""

    MD_WEEKLY_RELIABILITY = """# {{ title }}

**Weekly Reliability Report**

**Period:** {{ period_start | format_date }} - {{ period_end | format_date }}

---

{% if executive_summary %}
## 📋 Executive Summary

{{ executive_summary }}

{% endif %}
{% if metrics %}
## 📊 Weekly Metrics

| Metric | Value | WoW Change |
|--------|-------|------------|
| Total Incidents | {{ metrics.total_incidents }} | {{ metrics.incident_count_change_percent | format_percent if metrics.incident_count_change_percent is not none else 'N/A' }} |
| Mean MTTR | {{ metrics.mean_mttr_minutes | format_duration }} | {{ metrics.mttr_change_percent | format_percent if metrics.mttr_change_percent is not none else 'N/A' }} |
| P90 MTTR | {{ metrics.p90_mttr_minutes | format_duration }} | - |
| Trend | {{ metrics.trend | trend_arrow }} {{ metrics.trend | title }} | - |

{% if metrics.incidents_by_service %}
### By Service
{% for service, count in metrics.incidents_by_service.items() %}
- **{{ service }}**: {{ count }} incidents
{% endfor %}
{% endif %}

{% endif %}
{% if trends %}
## 📈 Trends

{% for trend_name, trend_data in trends.items() %}
- **{{ trend_name | replace('_', ' ') | title }}**: {{ trend_data }}
{% endfor %}

{% endif %}
{% if incidents %}
## 🚨 Top Incidents

| Severity | Service | Title | MTTR | Root Cause |
|----------|---------|-------|------|------------|
{% for incident in incidents[:10] %}
| {{ incident.severity | severity_emoji }} {{ incident.severity }} | {{ incident.service_name }} | {{ incident.title[:35] }}{% if incident.title|length > 35 %}...{% endif %} | {{ incident.duration_minutes | format_duration }} | {{ incident.root_cause[:25] if incident.root_cause else 'TBD' }}{% if incident.root_cause and incident.root_cause|length > 25 %}...{% endif %} |
{% endfor %}

{% endif %}
{% if ai_insights %}
## 💡 Weekly Insights

{% for insight in ai_insights %}
> {{ insight }}

{% endfor %}
{% endif %}

{% if ai_recommendations %}
## ✅ Action Items

{% for rec in ai_recommendations %}
- [ ] {{ rec }}
{% endfor %}
{% endif %}

---

{% if footer %}{{ footer }}{% else %}*Generated by Incident Copilot at {{ generated_at | format_datetime }}*{% endif %}
"""

    MD_MONTHLY_ANALYSIS = """# {{ title }}

**Monthly Reliability Analysis**

**Period:** {{ period_start | format_date }} - {{ period_end | format_date }}

---

{% if executive_summary %}
## 📋 Executive Summary

{{ executive_summary }}

{% endif %}
{% if metrics %}
## 📊 Monthly Overview

| Metric | Value | MoM Change |
|--------|-------|------------|
| Total Incidents | {{ metrics.total_incidents }} | {{ metrics.incident_count_change_percent | format_percent if metrics.incident_count_change_percent is not none else 'N/A' }} |
| Mean MTTR | {{ metrics.mean_mttr_minutes | format_duration }} | {{ metrics.mttr_change_percent | format_percent if metrics.mttr_change_percent is not none else 'N/A' }} |
| Median MTTR | {{ metrics.median_mttr_minutes | format_duration }} | - |
| P90 MTTR | {{ metrics.p90_mttr_minutes | format_duration }} | - |

{% endif %}
{% if trends %}
## 📈 Monthly Trends

{% for trend_name, trend_data in trends.items() %}
- **{{ trend_name | replace('_', ' ') | title }}**: {{ trend_data }}
{% endfor %}

{% endif %}
{% if ai_insights %}
## 💡 AI Analysis

{% for insight in ai_insights %}
> {{ insight }}

{% endfor %}
{% endif %}

{% if ai_recommendations %}
## ✅ Strategic Recommendations

{% for rec in ai_recommendations %}
- [ ] {{ rec }}
{% endfor %}
{% endif %}

---

{% if footer %}{{ footer }}{% else %}*Generated by Incident Copilot at {{ generated_at | format_datetime }}*{% endif %}
"""

    MD_INCIDENT_SUMMARY = """# {{ title }}

**Incident Summary Report**

---

## 🚨 Incidents ({{ incidents | length }})

| ID | Severity | Service | Title | Duration | Status |
|----|----------|---------|-------|----------|--------|
{% for incident in incidents %}
| `{{ incident.incident_id[:8] }}` | {{ incident.severity | severity_emoji }} {{ incident.severity }} | {{ incident.service_name }} | {{ incident.title[:35] }}{% if incident.title|length > 35 %}...{% endif %} | {{ incident.duration_minutes | format_duration }} | {{ 'Resolved' if incident.resolved_at else 'Active' }} |
{% endfor %}

---

{% if footer %}{{ footer }}{% else %}*Generated by Incident Copilot at {{ generated_at | format_datetime }}*{% endif %}
"""

    MD_SLA_REPORT = """# {{ title }}

**SLA Compliance Report**

**Period:** {{ period_start | format_date }} - {{ period_end | format_date }}

---

{% if metrics %}
## 📊 SLA Overview

| Metric | Value |
|--------|-------|
| Total Incidents | {{ metrics.total_incidents }} |
| SLA Met | {{ sla_met_count | default(0) }} |
| SLA Breached | {{ sla_breached_count | default(0) }} |
| Compliance Rate | {{ sla_compliance_percent | default('N/A') }}% |

{% endif %}
{% if sla_by_severity %}
## 📈 SLA by Severity

| Severity | Target MTTR | Actual MTTR | Compliance | Status |
|----------|-------------|-------------|------------|--------|
{% for sla in sla_by_severity %}
| {{ sla.severity | severity_emoji }} {{ sla.severity }} | {{ sla.target_mttr | format_duration }} | {{ sla.actual_mttr | format_duration }} | {{ sla.compliance }}% | {{ '✅ MET' if sla.met else '❌ BREACHED' }} |
{% endfor %}

{% endif %}
{% if breached_incidents %}
## ⚠️ SLA Breached Incidents

| Severity | Service | Title | Target | Actual | Breach |
|----------|---------|-------|--------|--------|--------|
{% for incident in breached_incidents %}
| {{ incident.severity | severity_emoji }} {{ incident.severity }} | {{ incident.service_name }} | {{ incident.title[:30] }}... | {{ incident.target_mttr | format_duration }} | {{ incident.actual_mttr | format_duration }} | +{{ incident.breach_amount | format_duration }} |
{% endfor %}
{% endif %}

---

{% if footer %}{{ footer }}{% else %}*Generated by Incident Copilot at {{ generated_at | format_datetime }}*{% endif %}
"""


# Global templates instance
report_templates = ReportTemplates()
