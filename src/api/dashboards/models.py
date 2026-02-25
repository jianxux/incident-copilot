"""Dashboard and Widget models for incident-copilot."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class WidgetType(StrEnum):
    COUNTER = "counter"
    CHART = "chart"
    LIST = "list"
    TIMELINE = "timeline"
    HEATMAP = "heatmap"


class ChartType(StrEnum):
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    AREA = "area"
    DONUT = "donut"


class AggregationType(StrEnum):
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    P95 = "p95"
    P99 = "p99"


class ShareScope(StrEnum):
    PRIVATE = "private"
    TEAM = "team"
    ORGANIZATION = "organization"
    PUBLIC = "public"


class DateRangePreset(StrEnum):
    LAST_15M = "15m"
    LAST_1H = "1h"
    LAST_6H = "6h"
    LAST_24H = "24h"
    LAST_7D = "7d"
    LAST_30D = "30d"
    CUSTOM = "custom"


class GridPosition(BaseModel):
    x: int = Field(ge=0, le=11)
    y: int = Field(ge=0)
    w: int = Field(ge=1, le=12, default=4)
    h: int = Field(ge=1, le=10, default=3)


class DateRange(BaseModel):
    preset: DateRangePreset = DateRangePreset.LAST_24H
    start: datetime | None = None
    end: datetime | None = None


class WidgetDataSource(BaseModel):
    metric: str
    filters: dict[str, Any] = Field(default_factory=dict)
    group_by: list[str] = Field(default_factory=list)
    aggregation: AggregationType = AggregationType.COUNT


class WidgetConfig(BaseModel):
    widget_type: WidgetType
    data_source: WidgetDataSource
    chart_type: ChartType | None = None
    show_legend: bool = True
    stacked: bool = False
    threshold_warning: float | None = None
    threshold_critical: float | None = None
    trend_enabled: bool = True
    page_size: int = Field(default=10, ge=1, le=100)
    columns: list[str] = Field(default_factory=list)
    show_severity: bool = True
    group_by_service: bool = False
    color_scheme: str = "severity"


class WidgetCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    config: WidgetConfig
    position: GridPosition
    refresh_interval_seconds: int = Field(default=60, ge=10, le=3600)
    date_range: DateRange = Field(default_factory=DateRange)


class WidgetUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    config: WidgetConfig | None = None
    position: GridPosition | None = None
    refresh_interval_seconds: int | None = None
    date_range: DateRange | None = None


class Widget(WidgetCreate):
    id: UUID = Field(default_factory=uuid4)
    dashboard_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DashboardLayout(BaseModel):
    columns: int = Field(default=12, ge=6, le=24)
    row_height: int = Field(default=80, ge=40, le=200)
    compact_type: str = "vertical"


class ShareConfig(BaseModel):
    scope: ShareScope = ShareScope.PRIVATE
    team_ids: list[UUID] = Field(default_factory=list)
    shared_with_users: list[UUID] = Field(default_factory=list)
    public_token: str | None = None
    expires_at: datetime | None = None
    allow_edit: bool = False


class DashboardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    layout: DashboardLayout = Field(default_factory=DashboardLayout)
    tags: list[str] = Field(default_factory=list)
    is_default: bool = False
    role: str | None = None
    widgets: list[WidgetCreate] = Field(default_factory=list)


class DashboardUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    layout: DashboardLayout | None = None
    tags: list[str] | None = None


class Dashboard(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str
    description: str | None = None
    layout: DashboardLayout = Field(default_factory=DashboardLayout)
    tags: list[str] = Field(default_factory=list)
    is_default: bool = False
    role: str | None = None
    widgets: list[Widget] = Field(default_factory=list)
    share_config: ShareConfig = Field(default_factory=ShareConfig)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cloned_from: UUID | None = None


class DashboardSummary(BaseModel):
    id: UUID
    name: str
    description: str | None
    owner_id: UUID
    widget_count: int
    share_scope: ShareScope
    tags: list[str]
    updated_at: datetime
