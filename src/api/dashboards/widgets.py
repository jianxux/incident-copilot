"""Widget type implementations and data fetching."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from .models import (
    AggregationType,
    ChartType,
    DateRange,
    DateRangePreset,
    Widget,
    WidgetConfig,
    WidgetType,
)


def resolve_date_range(date_range: DateRange) -> tuple[datetime, datetime]:
    """Resolve date range to actual start/end datetimes."""
    now = datetime.utcnow()
    if date_range.preset == DateRangePreset.CUSTOM:
        return date_range.start or now - timedelta(days=1), date_range.end or now
    
    preset_deltas = {
        DateRangePreset.LAST_15M: timedelta(minutes=15),
        DateRangePreset.LAST_1H: timedelta(hours=1),
        DateRangePreset.LAST_6H: timedelta(hours=6),
        DateRangePreset.LAST_24H: timedelta(days=1),
        DateRangePreset.LAST_7D: timedelta(days=7),
        DateRangePreset.LAST_30D: timedelta(days=30),
        DateRangePreset.LAST_90D: timedelta(days=90),
    }
    delta = preset_deltas.get(date_range.preset, timedelta(days=1))
    return now - delta, now


class WidgetRenderer(ABC):
    """Base class for widget renderers."""
    
    @abstractmethod
    async def fetch_data(
        self, config: WidgetConfig, date_range: DateRange
    ) -> dict[str, Any]:
        """Fetch data for the widget."""
        pass
    
    @abstractmethod
    def validate_config(self, config: WidgetConfig) -> list[str]:
        """Validate widget configuration, return list of errors."""
        pass


class CounterRenderer(WidgetRenderer):
    """Renderer for counter/metric widgets."""
    
    async def fetch_data(
        self, config: WidgetConfig, date_range: DateRange
    ) -> dict[str, Any]:
        start, end = resolve_date_range(date_range)
        # In real implementation, query metrics service
        return {
            "value": 0,
            "previous_value": 0,
            "trend_percent": 0.0,
            "trend_direction": "stable",
            "threshold_status": "normal",
            "unit": config.data_source.metric.split(".")[-1],
            "time_range": {"start": start.isoformat(), "end": end.isoformat()},
        }
    
    def validate_config(self, config: WidgetConfig) -> list[str]:
        errors = []
        if not config.data_source.metric:
            errors.append("Counter widget requires a metric")
        if config.threshold_warning and config.threshold_critical:
            if config.threshold_warning >= config.threshold_critical:
                errors.append("Warning threshold must be less than critical")
        return errors


class ChartRenderer(WidgetRenderer):
    """Renderer for chart widgets."""
    
    async def fetch_data(
        self, config: WidgetConfig, date_range: DateRange
    ) -> dict[str, Any]:
        start, end = resolve_date_range(date_range)
        chart_type = config.chart_type or ChartType.LINE
        
        # Base response structure for charts
        return {
            "chart_type": chart_type.value,
            "series": [],
            "labels": [],
            "time_range": {"start": start.isoformat(), "end": end.isoformat()},
            "aggregation": config.data_source.aggregation.value,
            "stacked": config.stacked,
        }
    
    def validate_config(self, config: WidgetConfig) -> list[str]:
        errors = []
        if not config.chart_type:
            errors.append("Chart widget requires chart_type")
        if config.chart_type in (ChartType.PIE, ChartType.DONUT):
            if config.stacked:
                errors.append("Pie/donut charts cannot be stacked")
        return errors


class ListRenderer(WidgetRenderer):
    """Renderer for incident list widgets."""
    
    async def fetch_data(
        self, config: WidgetConfig, date_range: DateRange
    ) -> dict[str, Any]:
        start, end = resolve_date_range(date_range)
        return {
            "items": [],
            "total_count": 0,
            "page": 1,
            "page_size": config.page_size,
            "columns": config.columns or ["id", "title", "severity", "status", "created_at"],
            "time_range": {"start": start.isoformat(), "end": end.isoformat()},
        }
    
    def validate_config(self, config: WidgetConfig) -> list[str]:
        errors = []
        if config.page_size > 100:
            errors.append("Page size cannot exceed 100")
        return errors


class TimelineRenderer(WidgetRenderer):
    """Renderer for timeline widgets."""
    
    async def fetch_data(
        self, config: WidgetConfig, date_range: DateRange
    ) -> dict[str, Any]:
        start, end = resolve_date_range(date_range)
        return {
            "events": [],
            "time_range": {"start": start.isoformat(), "end": end.isoformat()},
            "show_severity": config.show_severity,
            "grouped_by_service": config.group_by_service,
            "services": [],
        }
    
    def validate_config(self, config: WidgetConfig) -> list[str]:
        return []


class HeatmapRenderer(WidgetRenderer):
    """Renderer for heatmap widgets."""
    
    async def fetch_data(
        self, config: WidgetConfig, date_range: DateRange
    ) -> dict[str, Any]:
        start, end = resolve_date_range(date_range)
        return {
            "cells": [],
            "x_labels": [],
            "y_labels": [],
            "color_scheme": config.color_scheme,
            "max_value": 0,
            "min_value": 0,
            "time_range": {"start": start.isoformat(), "end": end.isoformat()},
        }
    
    def validate_config(self, config: WidgetConfig) -> list[str]:
        errors = []
        valid_schemes = ["severity", "gradient", "categorical"]
        if config.color_scheme not in valid_schemes:
            errors.append(f"Invalid color scheme. Use: {valid_schemes}")
        return errors


# Widget renderer registry
WIDGET_RENDERERS: dict[WidgetType, type[WidgetRenderer]] = {
    WidgetType.COUNTER: CounterRenderer,
    WidgetType.CHART: ChartRenderer,
    WidgetType.LIST: ListRenderer,
    WidgetType.TIMELINE: TimelineRenderer,
    WidgetType.HEATMAP: HeatmapRenderer,
}


def get_renderer(widget_type: WidgetType) -> WidgetRenderer:
    """Get renderer instance for widget type."""
    renderer_cls = WIDGET_RENDERERS.get(widget_type)
    if not renderer_cls:
        raise ValueError(f"Unknown widget type: {widget_type}")
    return renderer_cls()


async def fetch_widget_data(widget: Widget) -> dict[str, Any]:
    """Fetch data for a widget."""
    renderer = get_renderer(widget.config.widget_type)
    data = await renderer.fetch_data(widget.config, widget.date_range)
    return {
        "widget_id": str(widget.id),
        "widget_type": widget.config.widget_type.value,
        "title": widget.title,
        "data": data,
        "fetched_at": datetime.utcnow().isoformat(),
        "refresh_interval": widget.refresh_interval_seconds,
    }


def validate_widget_config(config: WidgetConfig) -> list[str]:
    """Validate widget configuration."""
    renderer = get_renderer(config.widget_type)
    return renderer.validate_config(config)
