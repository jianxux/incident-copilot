"""Default dashboard templates by role."""

from .models import (
    ChartType,
    DashboardCreate,
    DashboardLayout,
    GridPosition,
    WidgetConfig,
    WidgetCreate,
    WidgetDataSource,
    WidgetType,
)


def _widget(
    title: str, wtype: WidgetType, metric: str, x: int, y: int, w: int = 3, h: int = 2, **kw
) -> WidgetCreate:
    return WidgetCreate(
        title=title,
        config=WidgetConfig(widget_type=wtype, data_source=WidgetDataSource(metric=metric), **kw),
        position=GridPosition(x=x, y=y, w=w, h=h),
    )


def _counter(title: str, metric: str, x: int, y: int, **kw) -> WidgetCreate:
    return _widget(title, WidgetType.COUNTER, metric, x, y, 3, 2, **kw)


def _chart(
    title: str, metric: str, ct: ChartType, x: int, y: int, w: int = 6, h: int = 3, **kw
) -> WidgetCreate:
    return _widget(title, WidgetType.CHART, metric, x, y, w, h, chart_type=ct, **kw)


def _list(
    title: str, metric: str, x: int, y: int, w: int = 6, h: int = 4, cols: list[str] | None = None
) -> WidgetCreate:
    return _widget(
        title, WidgetType.LIST, metric, x, y, w, h, columns=cols or ["title", "severity", "status"]
    )


def _timeline(
    title: str, metric: str, x: int, y: int, w: int = 12, h: int = 3, grouped: bool = False
) -> WidgetCreate:
    return _widget(title, WidgetType.TIMELINE, metric, x, y, w, h, group_by_service=grouped)


def _heatmap(
    title: str, metric: str, x: int, y: int, w: int = 6, h: int = 4, scheme: str = "severity"
) -> WidgetCreate:
    return _widget(title, WidgetType.HEATMAP, metric, x, y, w, h, color_scheme=scheme)


EXECUTIVE_DASHBOARD = DashboardCreate(
    name="Executive Overview",
    description="High-level metrics for leadership",
    is_default=True,
    role="executive",
    tags=["default", "executive"],
    layout=DashboardLayout(row_height=100),
    widgets=[
        _counter("Active Incidents", "incidents.active", 0, 0),
        _counter("P1 Incidents", "incidents.p1", 3, 0, threshold_critical=1),
        _counter("MTTR (hours)", "incidents.mttr", 6, 0, threshold_warning=4, threshold_critical=8),
        _counter("SLA Compliance %", "incidents.sla", 9, 0),
        _chart("Incidents Over Time", "incidents.created", ChartType.AREA, 0, 2, 8),
        _chart("By Severity", "incidents.severity", ChartType.DONUT, 8, 2, 4),
        _timeline("Recent Incidents", "incidents.timeline", 0, 5),
    ],
)

ONCALL_DASHBOARD = DashboardCreate(
    name="On-Call Dashboard",
    description="Real-time view for on-call engineers",
    is_default=True,
    role="oncall",
    tags=["default", "oncall"],
    layout=DashboardLayout(),
    widgets=[
        _counter("Open", "incidents.open", 0, 0),
        _counter(
            "Unacknowledged", "incidents.unacked", 3, 0, threshold_warning=3, threshold_critical=5
        ),
        _counter("Assigned to Me", "incidents.mine", 6, 0),
        _counter("Avg Response", "incidents.response", 9, 0),
        _list(
            "Active Incidents",
            "incidents.active",
            0,
            2,
            6,
            5,
            ["severity", "title", "service", "duration"],
        ),
        _list("Recent Alerts", "alerts.recent", 6, 2, 6, 5, ["time", "source", "message"]),
        _chart("By Service", "incidents.by_service", ChartType.BAR, 0, 7),
        _heatmap("Service Health", "services.health", 6, 7),
    ],
)

SRE_DASHBOARD = DashboardCreate(
    name="SRE Dashboard",
    description="Detailed metrics for SRE team",
    is_default=True,
    role="sre",
    tags=["default", "sre"],
    layout=DashboardLayout(),
    widgets=[
        _counter("Error Budget", "slo.error_budget", 0, 0),
        _counter("Availability", "slo.availability", 3, 0),
        _counter("Burn Rate", "slo.burn_rate", 6, 0, threshold_warning=1, threshold_critical=2),
        _counter("MTTD (min)", "incidents.mttd", 9, 0),
        _chart("Error Rate", "metrics.error_rate", ChartType.LINE, 0, 2),
        _chart("Latency P99", "metrics.latency.p99", ChartType.LINE, 6, 2),
        _heatmap("Incidents by Hour", "incidents.by_hour", 0, 5, 6, 4, "gradient"),
        _chart("Top Error Sources", "errors.by_source", ChartType.BAR, 6, 5),
        _timeline("Deployments & Incidents", "events.timeline", 0, 9, 12, 3, True),
    ],
)

MANAGER_DASHBOARD = DashboardCreate(
    name="Team Manager Dashboard",
    description="Team performance metrics",
    is_default=True,
    role="manager",
    tags=["default", "manager"],
    layout=DashboardLayout(row_height=90),
    widgets=[
        _counter("Team Incidents", "incidents.team", 0, 0),
        _counter("Avg Handle Time", "incidents.handle_time", 3, 0),
        _counter("Team MTTR", "incidents.team.mttr", 6, 0),
        _counter("Escalations", "incidents.escalations", 9, 0),
        _chart("By Assignee", "incidents.by_assignee", ChartType.BAR, 0, 2),
        _chart("Weekly Trend", "incidents.weekly", ChartType.AREA, 6, 2),
        _list("Stale Incidents", "incidents.stale", 0, 5, 6, 4, ["title", "age", "assignee"]),
        _list(
            "SLA At Risk", "incidents.sla_risk", 6, 5, 6, 4, ["title", "sla_remaining", "assignee"]
        ),
    ],
)

DEFAULT_DASHBOARDS = {
    "executive": EXECUTIVE_DASHBOARD,
    "oncall": ONCALL_DASHBOARD,
    "sre": SRE_DASHBOARD,
    "manager": MANAGER_DASHBOARD,
}


def get_default_dashboard(role: str) -> DashboardCreate | None:
    return DEFAULT_DASHBOARDS.get(role)


def get_all_default_roles() -> list[str]:
    return list(DEFAULT_DASHBOARDS.keys())
