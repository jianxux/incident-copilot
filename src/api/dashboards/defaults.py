"""Default dashboard templates by role."""

from .models import (
    AggregationType,
    ChartType,
    DashboardCreate,
    DashboardLayout,
    GridPosition,
    WidgetConfig,
    WidgetCreate,
    WidgetDataSource,
    WidgetType,
)

# --- Widget Factory Helpers ---


def counter_widget(
    title: str,
    metric: str,
    x: int,
    y: int,
    w: int = 3,
    h: int = 2,
    warning: float | None = None,
    critical: float | None = None,
) -> WidgetCreate:
    """Create a counter widget."""
    return WidgetCreate(
        title=title,
        config=WidgetConfig(
            widget_type=WidgetType.COUNTER,
            data_source=WidgetDataSource(metric=metric),
            threshold_warning=warning,
            threshold_critical=critical,
        ),
        position=GridPosition(x=x, y=y, w=w, h=h),
    )


def chart_widget(
    title: str,
    metric: str,
    chart_type: ChartType,
    x: int,
    y: int,
    w: int = 6,
    h: int = 3,
    group_by: list[str] | None = None,
    stacked: bool = False,
) -> WidgetCreate:
    """Create a chart widget."""
    return WidgetCreate(
        title=title,
        config=WidgetConfig(
            widget_type=WidgetType.CHART,
            chart_type=chart_type,
            data_source=WidgetDataSource(
                metric=metric,
                group_by=group_by or [],
            ),
            stacked=stacked,
        ),
        position=GridPosition(x=x, y=y, w=w, h=h),
    )


def list_widget(
    title: str,
    metric: str,
    x: int,
    y: int,
    w: int = 6,
    h: int = 4,
    columns: list[str] | None = None,
    page_size: int = 10,
) -> WidgetCreate:
    """Create a list widget."""
    return WidgetCreate(
        title=title,
        config=WidgetConfig(
            widget_type=WidgetType.LIST,
            data_source=WidgetDataSource(metric=metric),
            columns=columns or ["title", "severity", "status", "assigned_to"],
            page_size=page_size,
        ),
        position=GridPosition(x=x, y=y, w=w, h=h),
    )


def timeline_widget(
    title: str,
    metric: str,
    x: int,
    y: int,
    w: int = 12,
    h: int = 3,
    group_by_service: bool = False,
) -> WidgetCreate:
    """Create a timeline widget."""
    return WidgetCreate(
        title=title,
        config=WidgetConfig(
            widget_type=WidgetType.TIMELINE,
            data_source=WidgetDataSource(metric=metric),
            group_by_service=group_by_service,
        ),
        position=GridPosition(x=x, y=y, w=w, h=h),
    )


def heatmap_widget(
    title: str,
    metric: str,
    x: int,
    y: int,
    w: int = 6,
    h: int = 4,
    color_scheme: str = "severity",
) -> WidgetCreate:
    """Create a heatmap widget."""
    return WidgetCreate(
        title=title,
        config=WidgetConfig(
            widget_type=WidgetType.HEATMAP,
            data_source=WidgetDataSource(metric=metric),
            color_scheme=color_scheme,
        ),
        position=GridPosition(x=x, y=y, w=w, h=h),
    )


# --- Default Dashboard Templates ---

EXECUTIVE_DASHBOARD = DashboardCreate(
    name="Executive Overview",
    description="High-level incident metrics for leadership",
    is_default=True,
    role="executive",
    tags=["default", "executive", "overview"],
    layout=DashboardLayout(columns=12, row_height=100),
    widgets=[
        counter_widget("Active Incidents", "incidents.active.count", 0, 0),
        counter_widget("P1 Incidents", "incidents.p1.count", 3, 0, critical=1),
        counter_widget("MTTR (hours)", "incidents.mttr.avg", 6, 0, warning=4, critical=8),
        counter_widget("SLA Compliance", "incidents.sla.percent", 9, 0, warning=95, critical=90),
        chart_widget("Incidents Over Time", "incidents.created", ChartType.AREA, 0, 2, 8, 3),
        chart_widget("By Severity", "incidents.severity", ChartType.DONUT, 8, 2, 4, 3),
        timeline_widget("Recent Incidents", "incidents.timeline", 0, 5, 12, 3),
    ],
)

ONCALL_DASHBOARD = DashboardCreate(
    name="On-Call Dashboard",
    description="Real-time view for on-call engineers",
    is_default=True,
    role="oncall",
    tags=["default", "oncall", "realtime"],
    layout=DashboardLayout(columns=12, row_height=80),
    widgets=[
        counter_widget("Open Incidents", "incidents.open.count", 0, 0),
        counter_widget("Unacknowledged", "incidents.unacked.count", 3, 0, warning=3, critical=5),
        counter_widget("Assigned to Me", "incidents.mine.count", 6, 0),
        counter_widget("Avg Response Time", "incidents.response.avg", 9, 0),
        list_widget(
            "Active Incidents",
            "incidents.active",
            0, 2, 6, 5,
            columns=["severity", "title", "service", "duration", "actions"],
        ),
        list_widget(
            "Recent Alerts",
            "alerts.recent",
            6, 2, 6, 5,
            columns=["time", "source", "message", "status"],
        ),
        chart_widget(
            "Incidents by Service",
            "incidents.by_service",
            ChartType.BAR,
            0, 7, 6, 3,
            group_by=["service"],
        ),
        heatmap_widget("Service Health", "services.health", 6, 7, 6, 3),
    ],
)

SRE_DASHBOARD = DashboardCreate(
    name="SRE Dashboard",
    description="Detailed metrics for SRE team",
    is_default=True,
    role="sre",
    tags=["default", "sre", "engineering"],
    layout=DashboardLayout(columns=12, row_height=80),
    widgets=[
        counter_widget("Error Budget", "slo.error_budget.remaining", 0, 0),
        counter_widget("Availability", "slo.availability.current", 3, 0),
        counter_widget("Burn Rate", "slo.burn_rate.current", 6, 0, warning=1, critical=2),
        counter_widget("MTTD (min)", "incidents.mttd.avg", 9, 0),
        chart_widget("Error Rate", "metrics.error_rate", ChartType.LINE, 0, 2, 6, 3),
        chart_widget("Latency P99", "metrics.latency.p99", ChartType.LINE, 6, 2, 6, 3),
        heatmap_widget("Incidents by Hour", "incidents.by_hour", 0, 5, 6, 4, "gradient"),
        chart_widget(
            "Top Error Sources",
            "errors.by_source",
            ChartType.BAR,
            6, 5, 6, 4,
            group_by=["source"],
        ),
        timeline_widget("Deployments & Incidents", "events.timeline", 0, 9, 12, 3, True),
    ],
)

MANAGER_DASHBOARD = DashboardCreate(
    name="Team Manager Dashboard",
    description="Team performance and workload metrics",
    is_default=True,
    role="manager",
    tags=["default", "manager", "team"],
    layout=DashboardLayout(columns=12, row_height=90),
    widgets=[
        counter_widget("Team Incidents", "incidents.team.count", 0, 0),
        counter_widget("Avg Handle Time", "incidents.handle_time.avg", 3, 0),
        counter_widget("Team MTTR", "incidents.team.mttr", 6, 0),
        counter_widget("Escalations", "incidents.escalations.count", 9, 0),
        chart_widget(
            "Incidents by Team Member",
            "incidents.by_assignee",
            ChartType.BAR,
            0, 2, 6, 3,
            group_by=["assignee"],
        ),
        chart_widget("Weekly Trend", "incidents.weekly", ChartType.AREA, 6, 2, 6, 3),
        list_widget(
            "Stale Incidents",
            "incidents.stale",
            0, 5, 6, 4,
            columns=["title", "age", "assignee", "last_update"],
        ),
        list_widget(
            "SLA At Risk",
            "incidents.sla_risk",
            6, 5, 6, 4,
            columns=["title", "sla_remaining", "severity", "assignee"],
        ),
    ],
)

# Registry of default dashboards by role
DEFAULT_DASHBOARDS: dict[str, DashboardCreate] = {
    "executive": EXECUTIVE_DASHBOARD,
    "oncall": ONCALL_DASHBOARD,
    "sre": SRE_DASHBOARD,
    "manager": MANAGER_DASHBOARD,
}


def get_default_dashboard(role: str) -> DashboardCreate | None:
    """Get default dashboard template for a role."""
    return DEFAULT_DASHBOARDS.get(role)


def get_all_default_roles() -> list[str]:
    """Get all roles with default dashboards."""
    return list(DEFAULT_DASHBOARDS.keys())
