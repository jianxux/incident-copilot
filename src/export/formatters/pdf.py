"""PDF export formatter using reportlab."""

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, LEGAL, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..models import (
    ColumnConfig,
    ExportType,
    PDFOptions,
    RelatedDataConfig,
)


class PDFFormatter:
    """Formatter for PDF exports using ReportLab."""

    PAGE_SIZES = {
        "A4": A4,
        "Letter": LETTER,
        "Legal": LEGAL,
    }

    def __init__(
        self,
        export_type: ExportType,
        columns: list[ColumnConfig] | None = None,
        options: PDFOptions | None = None,
        related_data: RelatedDataConfig | None = None,
    ):
        self.export_type = export_type
        self.columns = columns or []
        self.options = options or PDFOptions()
        self.related_data = related_data or RelatedDataConfig()
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self) -> None:
        """Set up custom paragraph styles."""
        self.styles.add(
            ParagraphStyle(
                name="CustomTitle",
                parent=self.styles["Title"],
                fontSize=24,
                spaceAfter=30,
                alignment=TA_CENTER,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="CustomHeading1",
                parent=self.styles["Heading1"],
                fontSize=18,
                spaceAfter=12,
                spaceBefore=20,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="CustomHeading2",
                parent=self.styles["Heading2"],
                fontSize=14,
                spaceAfter=8,
                spaceBefore=15,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="CustomHeading3",
                parent=self.styles["Heading3"],
                fontSize=12,
                spaceAfter=6,
                spaceBefore=10,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="CustomBody",
                parent=self.styles["Normal"],
                fontSize=self.options.font_size,
                spaceAfter=6,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TableCell",
                parent=self.styles["Normal"],
                fontSize=self.options.font_size - 1,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="Footer",
                parent=self.styles["Normal"],
                fontSize=8,
                alignment=TA_CENTER,
                textColor=colors.grey,
            )
        )

    def _get_page_size(self) -> tuple:
        """Get page size based on options."""
        size = self.PAGE_SIZES.get(self.options.page_size, A4)
        if self.options.orientation == "landscape":
            return size[1], size[0]
        return size

    def format(self, data: list[dict[str, Any]] | dict[str, Any]) -> bytes:
        """Format data as PDF bytes."""
        buffer = BytesIO()
        page_size = self._get_page_size()
        margins = self.options.margins

        doc = SimpleDocTemplate(
            buffer,
            pagesize=page_size,
            topMargin=margins.get("top", 72),
            bottomMargin=margins.get("bottom", 72),
            leftMargin=margins.get("left", 72),
            rightMargin=margins.get("right", 72),
        )

        # Build content
        story = []

        # Cover page
        if self.options.include_cover_page:
            story.extend(self._build_cover_page())

        # Table of Contents
        if self.options.include_toc:
            story.extend(self._build_toc(data))

        # Main content
        if self.export_type == ExportType.INCIDENTS:
            story.extend(
                self._build_incidents_content(
                    data if isinstance(data, list) else [data]
                )
            )
        elif self.export_type == ExportType.POSTMORTEMS:
            story.extend(
                self._build_postmortems_content(
                    data if isinstance(data, list) else [data]
                )
            )
        elif self.export_type == ExportType.ANALYTICS:
            story.extend(
                self._build_analytics_content(data if isinstance(data, dict) else {})
            )
        else:
            story.extend(
                self._build_generic_content(data if isinstance(data, list) else [data])
            )

        # Build with custom header/footer
        doc.build(
            story,
            onFirstPage=self._add_header_footer,
            onLaterPages=self._add_header_footer,
        )

        return buffer.getvalue()

    def format_bytes(self, data: list[dict[str, Any]] | dict[str, Any]) -> bytes:
        """Format data as PDF bytes (alias for format)."""
        return self.format(data)

    def _add_header_footer(self, canvas, doc) -> None:
        """Add header and footer to each page."""
        canvas.saveState()
        page_width, page_height = self._get_page_size()

        if self.options.include_header:
            header_text = self.options.header_text or "Incident Copilot Export"
            canvas.setFont("Helvetica", 9)
            canvas.setFillColor(colors.grey)
            canvas.drawString(
                doc.leftMargin,
                page_height - 40,
                header_text,
            )
            canvas.drawRightString(
                page_width - doc.rightMargin,
                page_height - 40,
                datetime.utcnow().strftime("%Y-%m-%d"),
            )

        if self.options.include_footer:
            footer_text = self.options.footer_text or "Generated by Incident Copilot"
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.grey)
            canvas.drawCentredString(
                page_width / 2,
                30,
                footer_text,
            )
            canvas.drawRightString(
                page_width - doc.rightMargin,
                30,
                f"Page {canvas.getPageNumber()}",
            )

        canvas.restoreState()

    def _build_cover_page(self) -> list:
        """Build cover page elements."""
        elements = []
        elements.append(Spacer(1, 2 * inch))

        title_map = {
            ExportType.INCIDENTS: "Incident Report",
            ExportType.POSTMORTEMS: "Postmortem Report",
            ExportType.ANALYTICS: "Analytics Report",
            ExportType.REPORTS: "System Report",
            ExportType.TIMELINE: "Timeline Report",
            ExportType.ACTION_ITEMS: "Action Items Report",
        }
        title = title_map.get(self.export_type, "Export Report")

        elements.append(Paragraph(title, self.styles["CustomTitle"]))
        elements.append(Spacer(1, 0.5 * inch))
        elements.append(
            Paragraph(
                f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                self.styles["CustomBody"],
            )
        )
        elements.append(Spacer(1, 0.25 * inch))
        elements.append(
            Paragraph(
                "Incident Copilot",
                self.styles["CustomBody"],
            )
        )
        elements.append(PageBreak())

        return elements

    def _build_toc(self, data: list[dict[str, Any]] | dict[str, Any]) -> list:
        """Build table of contents."""
        elements = []
        elements.append(Paragraph("Table of Contents", self.styles["CustomHeading1"]))
        elements.append(Spacer(1, 0.25 * inch))

        if isinstance(data, list):
            for i, item in enumerate(data, 1):
                if self.export_type == ExportType.INCIDENTS:
                    title = f"{i}. {item.get('incident_id', 'Unknown')}: {item.get('title', 'Untitled')}"
                elif self.export_type == ExportType.POSTMORTEMS:
                    title = f"{i}. {item.get('id', 'Unknown')}: {item.get('title', 'Untitled')}"
                else:
                    title = f"{i}. Item {i}"
                elements.append(Paragraph(title, self.styles["CustomBody"]))
        else:
            elements.append(Paragraph("1. Overview", self.styles["CustomBody"]))
            elements.append(Paragraph("2. Statistics", self.styles["CustomBody"]))
            elements.append(Paragraph("3. Breakdowns", self.styles["CustomBody"]))

        elements.append(PageBreak())
        return elements

    def _build_incidents_content(self, incidents: list[dict[str, Any]]) -> list:
        """Build incident content."""
        elements = []
        elements.append(Paragraph("Incidents", self.styles["CustomHeading1"]))

        for incident in incidents:
            elements.extend(self._build_incident(incident))

        return elements

    def _build_incident(self, incident: dict[str, Any]) -> list:
        """Build content for a single incident."""
        elements = []
        inc_id = incident.get("incident_id", "Unknown")
        title = incident.get("title", "Untitled")

        elements.append(
            Paragraph(
                f"{inc_id}: {title}",
                self.styles["CustomHeading2"],
            )
        )

        # Overview table
        overview_data = [
            ["Field", "Value"],
            ["Severity", str(incident.get("severity", "N/A"))],
            ["Service", str(incident.get("service_name", "N/A"))],
            ["Status", str(incident.get("status", "N/A"))],
            ["Triggered", self._format_datetime(incident.get("triggered_at"))],
            ["Resolved", self._format_datetime(incident.get("resolved_at"))],
        ]

        elements.append(self._create_table(overview_data))
        elements.append(Spacer(1, 0.2 * inch))

        # Timeline
        if self.related_data.include_timeline:
            timeline = incident.get("timeline", [])
            if timeline:
                elements.append(Paragraph("Timeline", self.styles["CustomHeading3"]))
                max_events = self.related_data.max_timeline_events
                display_timeline = timeline[:max_events] if max_events else timeline

                timeline_data = [["Time", "Event", "Type"]]
                for event in display_timeline:
                    timeline_data.append(
                        [
                            self._format_datetime(event.get("timestamp")),
                            str(event.get("title", ""))[:50],
                            str(event.get("event_type", "")),
                        ]
                    )

                elements.append(self._create_table(timeline_data))

                if max_events and len(timeline) > max_events:
                    elements.append(
                        Paragraph(
                            f"... and {len(timeline) - max_events} more events",
                            self.styles["CustomBody"],
                        )
                    )
                elements.append(Spacer(1, 0.2 * inch))

        # Action Items
        if self.related_data.include_action_items:
            actions = incident.get("action_items", [])
            if actions:
                elements.append(
                    Paragraph("Action Items", self.styles["CustomHeading3"])
                )
                action_data = [["Title", "Priority", "Status", "Owner"]]
                for action in actions:
                    action_data.append(
                        [
                            str(action.get("title", ""))[:40],
                            str(action.get("priority", "")),
                            str(action.get("status", "")),
                            str(action.get("owner", "N/A")),
                        ]
                    )
                elements.append(self._create_table(action_data))
                elements.append(Spacer(1, 0.2 * inch))

        elements.append(Spacer(1, 0.3 * inch))
        return elements

    def _build_postmortems_content(self, postmortems: list[dict[str, Any]]) -> list:
        """Build postmortem content."""
        elements = []
        elements.append(Paragraph("Postmortems", self.styles["CustomHeading1"]))

        for pm in postmortems:
            elements.extend(self._build_postmortem(pm))
            elements.append(PageBreak())

        return elements

    def _build_postmortem(self, pm: dict[str, Any]) -> list:
        """Build content for a single postmortem."""
        elements = []
        pm_id = pm.get("id", "Unknown")
        title = pm.get("title", "Untitled")

        elements.append(
            Paragraph(
                f"{pm_id}: {title}",
                self.styles["CustomHeading2"],
            )
        )

        # Overview
        overview_data = [
            ["Field", "Value"],
            ["Incident ID", str(pm.get("incident_id", "N/A"))],
            ["Service", str(pm.get("service_name", "N/A"))],
            ["Severity", str(pm.get("severity", "N/A"))],
            ["Status", str(pm.get("status", "N/A"))],
            ["Duration", f"{pm.get('incident_duration_minutes', 'N/A')} minutes"],
            ["Created", self._format_datetime(pm.get("created_at"))],
            ["Author", str(pm.get("created_by", "N/A"))],
        ]
        elements.append(self._create_table(overview_data))
        elements.append(Spacer(1, 0.2 * inch))

        # Executive Summary
        if pm.get("executive_summary"):
            elements.append(
                Paragraph("Executive Summary", self.styles["CustomHeading3"])
            )
            elements.append(
                Paragraph(pm["executive_summary"], self.styles["CustomBody"])
            )
            elements.append(Spacer(1, 0.2 * inch))

        # Root Cause
        if self.related_data.include_root_cause:
            root_cause = pm.get("root_cause", {})
            if root_cause:
                elements.append(
                    Paragraph("Root Cause Analysis", self.styles["CustomHeading3"])
                )
                elements.append(
                    Paragraph(
                        f"<b>Primary Cause:</b> {root_cause.get('primary_cause', 'N/A')}",
                        self.styles["CustomBody"],
                    )
                )
                if root_cause.get("trigger"):
                    elements.append(
                        Paragraph(
                            f"<b>Trigger:</b> {root_cause['trigger']}",
                            self.styles["CustomBody"],
                        )
                    )
                factors = root_cause.get("contributing_factors", [])
                if factors:
                    elements.append(
                        Paragraph(
                            "<b>Contributing Factors:</b>",
                            self.styles["CustomBody"],
                        )
                    )
                    for factor in factors:
                        elements.append(
                            Paragraph(
                                f"• {factor}",
                                self.styles["CustomBody"],
                            )
                        )
                elements.append(Spacer(1, 0.2 * inch))

        # Impact
        if self.related_data.include_impact:
            impact = pm.get("impact", {})
            if impact:
                elements.append(Paragraph("Impact", self.styles["CustomHeading3"]))
                impact_data = [
                    ["Metric", "Value"],
                    ["Severity", str(impact.get("severity", "N/A"))],
                    ["Duration", f"{impact.get('duration_minutes', 'N/A')} minutes"],
                    ["Users Affected", str(impact.get("users_affected", "N/A"))],
                    ["SLA Breach", "Yes" if impact.get("sla_breach") else "No"],
                ]
                elements.append(self._create_table(impact_data))
                elements.append(Spacer(1, 0.2 * inch))

        # Action Items
        if self.related_data.include_action_items:
            actions = pm.get("action_items", [])
            if actions:
                elements.append(
                    Paragraph("Action Items", self.styles["CustomHeading3"])
                )
                action_data = [["ID", "Title", "Priority", "Status", "Owner"]]
                for action in actions:
                    action_data.append(
                        [
                            str(action.get("id", "")),
                            str(action.get("title", ""))[:35],
                            str(action.get("priority", "")),
                            str(action.get("status", "")),
                            str(action.get("owner", "N/A")),
                        ]
                    )
                elements.append(self._create_table(action_data))
                elements.append(Spacer(1, 0.2 * inch))

        # Lessons Learned
        lessons = pm.get("lessons_learned", [])
        if lessons:
            elements.append(Paragraph("Lessons Learned", self.styles["CustomHeading3"]))
            for lesson in lessons:
                elements.append(Paragraph(f"• {lesson}", self.styles["CustomBody"]))
            elements.append(Spacer(1, 0.2 * inch))

        return elements

    def _build_analytics_content(self, analytics: dict[str, Any]) -> list:
        """Build analytics content."""
        elements = []
        elements.append(Paragraph("Analytics Overview", self.styles["CustomHeading1"]))

        # MTTR Stats
        if "mttr_stats" in analytics:
            stats = analytics["mttr_stats"]
            elements.append(Paragraph("MTTR Statistics", self.styles["CustomHeading2"]))
            elements.append(
                Paragraph(
                    f"Period: {stats.get('period', 'N/A')}",
                    self.styles["CustomBody"],
                )
            )

            mttr_data = [
                ["Metric", "Value"],
                [
                    "Mean MTTR",
                    (
                        f"{stats.get('mean_mttr_minutes', 'N/A'):.1f} min"
                        if stats.get("mean_mttr_minutes")
                        else "N/A"
                    ),
                ],
                [
                    "Median MTTR",
                    (
                        f"{stats.get('median_mttr_minutes', 'N/A'):.1f} min"
                        if stats.get("median_mttr_minutes")
                        else "N/A"
                    ),
                ],
                [
                    "P90 MTTR",
                    (
                        f"{stats.get('p90_mttr_minutes', 'N/A'):.1f} min"
                        if stats.get("p90_mttr_minutes")
                        else "N/A"
                    ),
                ],
                ["Total Incidents", str(stats.get("incidents_count", 0))],
                ["Resolved", str(stats.get("resolved_count", 0))],
            ]
            elements.append(self._create_table(mttr_data))
            elements.append(Spacer(1, 0.3 * inch))

        # Severity Breakdown
        if "severity_breakdown" in analytics:
            elements.append(
                Paragraph("Incidents by Severity", self.styles["CustomHeading2"])
            )
            sev_data = [["Severity", "Count"]]
            for sev, count in analytics["severity_breakdown"].items():
                sev_data.append([str(sev), str(count)])
            elements.append(self._create_table(sev_data))
            elements.append(Spacer(1, 0.3 * inch))

        # Service Breakdown
        if "service_breakdown" in analytics:
            elements.append(
                Paragraph("Incidents by Service", self.styles["CustomHeading2"])
            )
            svc_data = [["Service", "Count"]]
            for svc, count in analytics["service_breakdown"].items():
                svc_data.append([str(svc), str(count)])
            elements.append(self._create_table(svc_data))
            elements.append(Spacer(1, 0.3 * inch))

        return elements

    def _build_generic_content(self, data: list[dict[str, Any]]) -> list:
        """Build generic table content."""
        elements = []
        elements.append(Paragraph("Data Export", self.styles["CustomHeading1"]))

        if not data:
            elements.append(Paragraph("No data to export.", self.styles["CustomBody"]))
            return elements

        # Determine columns
        if self.columns:
            headers = [col.header or col.field for col in self.columns if col.include]
            fields = [col.field for col in self.columns if col.include]
        else:
            fields = list(data[0].keys())
            headers = fields

        # Build table
        table_data = [headers]
        for item in data:
            row = []
            for field in fields:
                value = item.get(field, "")
                if isinstance(value, datetime):
                    value = self._format_datetime(value)
                elif isinstance(value, (list, dict)):
                    import json

                    value = json.dumps(value)[:50]
                row.append(str(value) if value is not None else "")
            table_data.append(row)

        elements.append(self._create_table(table_data))
        return elements

    def _create_table(self, data: list[list[str]]) -> Table:
        """Create a styled table."""
        if not data:
            return Table([[""]])

        table = Table(data)

        style = TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a5568")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f7fafc")],
                ),
            ]
        )
        table.setStyle(style)

        return table

    def _format_datetime(self, dt: datetime | str | None) -> str:
        """Format datetime for display."""
        if dt is None:
            return "N/A"
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except ValueError:
                return dt
        return dt.strftime("%Y-%m-%d %H:%M")

    def format_incidents(self, incidents: list[dict[str, Any]]) -> bytes:
        """Format incident data as PDF."""
        return self.format(incidents)

    def format_postmortems(self, postmortems: list[dict[str, Any]]) -> bytes:
        """Format postmortem data as PDF."""
        return self.format(postmortems)

    def format_analytics(self, analytics: dict[str, Any]) -> bytes:
        """Format analytics data as PDF."""
        return self.format(analytics)
