"""Dashboard and Widget models for incident-copilot."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class WidgetType(str, Enum):
    """Supported widget types."""
    COUNTER = "counter"
    CHART = "chart"
    LIST = "list"
    TIMELINE = "timeline"
    HEATMAP = "heatmap"


class ChartType(str, Enum):
    """Chart subtypes for chart widgets."""
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    AREA = "area"
    DONUT = "donut"


class AggregationType(str, Enum):
    """Aggregation methods for metrics."""
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    P50 = "p50"
    P95 = "p95"
    P99 = "p99"


class ShareScope(str, Enum):
    """Dashboard sharing scope."""
    PRIVATE = "private"
    TEAM = "team"
    ORGANIZATION = "organization"
    PUBLIC = "public"


class DateRangePreset(str, Enum):
    """Predefined date range options."""
    LAST_15M = "15m"
    LAST_1H = "1h"
    LAST_6H = "6h"
    LAST_24H = "24h"
    LAST_7D = "7d"
    LAST_30D = "30d"
    LAST_90D = "90d"
    CUSTOM = "custom"


class GridPosition(BaseModel):
    """Widget position in dashboard grid."""
    x: int = Field(ge=0, le=11, description="Column position (0-11)")
    y: int = Field(ge=0, description="Row position")
    w: int = Field(ge=1, le=12, default=4, description="Width in columns")
    h: int = Field(ge=1, le=10, default=3, description="Height in rows")


class DateRange(BaseModel):
    """Date range filter for widgets."""
    preset: DateRangePreset = DateRangePreset.LAST_24H
    start: datetime | None = None
    end: datetime | None = None

    @field_validator("start", "end", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> datetime | None:
        if v is None or isinstance(v, datetime):
            return v
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


class WidgetDataSource(BaseModel):
    """Data source configuration for a widget."""
    metric: str = Field(..., description="Metric name or query identifier")
    filters: dict[str, Any] = Field(default_factory=dict)
    group_by: list[str] = Field(default_factory=list)
    aggregation: AggregationType = AggregationType.COUNT


class WidgetConfig(BaseModel):
    """Configuration for a specific widget type."""
    widget_type: WidgetType
    data_source: WidgetDataSource
    # Chart-specific
    chart_type: ChartType | None = None
    show_legend: bool = True
    stacked: bool = False
    # Counter-specific
    threshold_warning: float | None = None
    threshold_critical: float | None = None
    trend_enabled: bool = True
    # List-specific
    page_size: int = Field(default=10, ge=1, le=100)
    columns: list[str] = Field(default_factory=list)
    sortable: bool = True
    # Timeline-specific
    show_severity: bool = True
    group_by_service: bool = False
    # Heatmap-specific
    color_scheme: str = "severity"
    cell_size: int = Field(default=20, ge=10, le=50)


class WidgetBase(BaseModel):
    """Base widget model for creation."""
    title: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    config: WidgetConfig
    position: GridPosition
    refresh_interval_seconds: int = Field(default=60, ge=10, le=3600)
    date_range: DateRange = Field(default_factory=DateRange)


class WidgetCreate(WidgetBase):
    """Widget creation payload."""
    pass


class WidgetUpdate(BaseModel):
    """Widget update payload - all fields optional."""
    title: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    config: WidgetConfig | None = None
    position: GridPosition | None = None
    refresh_interval_seconds: int | None = Field(None, ge=10, le=3600)
    date_range: DateRange | None = None


class Widget(WidgetBase):
    """Full widget model with ID and timestamps."""
    id: UUID = Field(default_factory=uuid4)
    dashboard_id: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DashboardLayout(BaseModel):
    """Dashboard layout configuration."""
    columns: int = Field(default=12, ge=6, le=24)
    row_height: int = Field(default=80, ge=40, le=200)
    margin: tuple[int, int] = (10, 10)
    compact_type: str = Field(default="vertical", pattern="^(vertical|horizontal|none)$")


class ShareConfig(BaseModel):
    """Dashboard sharing configuration."""
    scope: ShareScope = ShareScope.PRIVATE
    team_ids: list[UUID] = Field(default_factory=list)
    shared_with_users: list[UUID] = Field(default_factory=list)
    public_token: str | None = None
    expires_at: datetime | None = None
    allow_edit: bool = False


class DashboardBase(BaseModel):
    """Base dashboard model."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    layout: DashboardLayout = Field(default_factory=DashboardLayout)
    tags: list[str] = Field(default_factory=list)
    is_default: bool = False
    role: str | None = Field(None, description="Role this dashboard is default for")


class DashboardCreate(DashboardBase):
    """Dashboard creation payload."""
    widgets: list[WidgetCreate] = Field(default_factory=list)


class DashboardUpdate(BaseModel):
    """Dashboard update payload."""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    layout: DashboardLayout | None = None
    tags: list[str] | None = None
    is_default: bool | None = None
    role: str | None = None


class Dashboard(DashboardBase):
    """Full dashboard model."""
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    widgets: list[Widget] = Field(default_factory=list)
    share_config: ShareConfig = Field(default_factory=ShareConfig)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    cloned_from: UUID | None = None


class DashboardSummary(BaseModel):
    """Lightweight dashboard info for listings."""
    id: UUID
    name: str
    description: str | None
    owner_id: UUID
    widget_count: int
    share_scope: ShareScope
    tags: list[str]
    is_default: bool
    role: str | None
    updated_at: datetime
