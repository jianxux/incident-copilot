"""Widget type implementations and data fetching."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import (
    ChartType,
    DateRange,
    DateRangePreset,
    Widget,
    WidgetConfig,
    WidgetType,
)

PRESET_DELTAS = {
    DateRangePreset.LAST_15M: timedelta(minutes=15),
    DateRangePreset.LAST_1H: timedelta(hours=1),
    DateRangePreset.LAST_6H: timedelta(hours=6),
    DateRangePreset.LAST_24H: timedelta(days=1),
    DateRangePreset.LAST_7D: timedelta(days=7),
    DateRangePreset.LAST_30D: timedelta(days=30),
}


def resolve_date_range(dr: DateRange) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if dr.preset == DateRangePreset.CUSTOM:
        return dr.start or now - timedelta(days=1), dr.end or now
    return now - PRESET_DELTAS.get(dr.preset, timedelta(days=1)), now


class WidgetRenderer(ABC):
    @abstractmethod
    async def fetch_data(self, cfg: WidgetConfig, dr: DateRange) -> dict[str, Any]:
        pass

    def validate(self, cfg: WidgetConfig) -> list[str]:
        return []


class CounterRenderer(WidgetRenderer):
    async def fetch_data(self, cfg: WidgetConfig, dr: DateRange) -> dict[str, Any]:
        s, e = resolve_date_range(dr)
        return {
            "value": 0,
            "previous": 0,
            "trend_percent": 0.0,
            "status": "normal",
            "time_range": {"start": s.isoformat(), "end": e.isoformat()},
        }

    def validate(self, cfg: WidgetConfig) -> list[str]:
        if (
            cfg.threshold_warning
            and cfg.threshold_critical
            and cfg.threshold_warning >= cfg.threshold_critical
        ):
            return ["Warning threshold must be < critical"]
        return []


class ChartRenderer(WidgetRenderer):
    async def fetch_data(self, cfg: WidgetConfig, dr: DateRange) -> dict[str, Any]:
        s, e = resolve_date_range(dr)
        return {
            "chart_type": (cfg.chart_type or ChartType.LINE).value,
            "series": [],
            "labels": [],
            "time_range": {"start": s.isoformat(), "end": e.isoformat()},
            "stacked": cfg.stacked,
        }

    def validate(self, cfg: WidgetConfig) -> list[str]:
        if cfg.chart_type in (ChartType.PIE, ChartType.DONUT) and cfg.stacked:
            return ["Pie/donut charts cannot be stacked"]
        return []


class ListRenderer(WidgetRenderer):
    async def fetch_data(self, cfg: WidgetConfig, dr: DateRange) -> dict[str, Any]:
        s, e = resolve_date_range(dr)
        return {
            "items": [],
            "total": 0,
            "page_size": cfg.page_size,
            "columns": cfg.columns or ["title", "severity", "status"],
            "time_range": {"start": s.isoformat(), "end": e.isoformat()},
        }


class TimelineRenderer(WidgetRenderer):
    async def fetch_data(self, cfg: WidgetConfig, dr: DateRange) -> dict[str, Any]:
        s, e = resolve_date_range(dr)
        return {
            "events": [],
            "grouped": cfg.group_by_service,
            "time_range": {"start": s.isoformat(), "end": e.isoformat()},
        }


class HeatmapRenderer(WidgetRenderer):
    async def fetch_data(self, cfg: WidgetConfig, dr: DateRange) -> dict[str, Any]:
        s, e = resolve_date_range(dr)
        return {
            "cells": [],
            "x_labels": [],
            "y_labels": [],
            "scheme": cfg.color_scheme,
            "time_range": {"start": s.isoformat(), "end": e.isoformat()},
        }

    def validate(self, cfg: WidgetConfig) -> list[str]:
        if cfg.color_scheme not in ("severity", "gradient", "categorical"):
            return ["Invalid color scheme"]
        return []


RENDERERS: dict[WidgetType, type[WidgetRenderer]] = {
    WidgetType.COUNTER: CounterRenderer,
    WidgetType.CHART: ChartRenderer,
    WidgetType.LIST: ListRenderer,
    WidgetType.TIMELINE: TimelineRenderer,
    WidgetType.HEATMAP: HeatmapRenderer,
}


def get_renderer(wt: WidgetType) -> WidgetRenderer:
    return RENDERERS[wt]()


async def fetch_widget_data(w: Widget) -> dict[str, Any]:
    data = await get_renderer(w.config.widget_type).fetch_data(w.config, w.date_range)
    return {
        "widget_id": str(w.id),
        "type": w.config.widget_type.value,
        "title": w.title,
        "data": data,
        "fetched_at": datetime.now(UTC).isoformat(),
        "refresh": w.refresh_interval_seconds,
    }


def validate_widget_config(cfg: WidgetConfig) -> list[str]:
    return get_renderer(cfg.widget_type).validate(cfg)
