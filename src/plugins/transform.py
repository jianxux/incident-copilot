"""Payload transformation utilities using Jinja2 templates."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog
from jinja2 import BaseLoader, Environment, TemplateSyntaxError, UndefinedError

logger = structlog.get_logger()


class PayloadTransformer:
    def __init__(self):
        self._env = Environment(
            loader=BaseLoader(),
            autoescape=False,  # nosec B701 - intentional for JSON payload transformation trim_blocks=True, lstrip_blocks=True
        )
        self._env.filters.update({
            "json": lambda x: json.dumps(x, default=str),
            "default": lambda x, d="": d if x is None or x == "" or x == [] else x,
            "truncate": self._truncate,
            "upper": lambda x: str(x).upper() if x else "",
            "lower": lambda x: str(x).lower() if x else "",
            "timestamp": self._timestamp,
            "severity_emoji": lambda s: {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢",
                "info": "🔵",
            }.get(str(s).lower(), "⚪"),
        })

    @staticmethod
    def _truncate(v: str, length: int = 100, suffix: str = "...") -> str:
        return "" if not v else v if len(v) <= length else v[: length - len(suffix)] + suffix

    @staticmethod
    def _timestamp(v: datetime | str | None, fmt: str = "iso") -> str:
        if v is None:
            return ""
        if isinstance(v, str):
            try:
                v = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                return v
        return {
            "iso": v.isoformat,
            "unix": lambda: str(int(v.timestamp())),
            "date": lambda: v.strftime("%Y-%m-%d"),
        }.get(fmt, lambda: v.strftime(fmt))()

    def transform(self, template: str, data: dict[str, Any], **extra: Any) -> dict[str, Any]:
        try:
            rendered = self._env.from_string(template).render(
                data=data, now=datetime.utcnow(), **data, **extra
            )
            return json.loads(rendered)
        except TemplateSyntaxError as e:
            raise ValueError(f"Template syntax error at line {e.lineno}: {e.message}")
        except UndefinedError as e:
            raise ValueError(f"Template undefined variable: {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Template did not produce valid JSON: {e}")

    def render_string(self, template: str, data: dict[str, Any], **extra: Any) -> str:
        try:
            return self._env.from_string(template).render(
                data=data, now=datetime.utcnow(), **data, **extra
            )
        except Exception:
            return template

    def validate_template(self, template: str) -> tuple[bool, str | None]:
        try:
            self._env.parse(template)
            return True, None
        except TemplateSyntaxError as e:
            return False, f"Syntax error at line {e.lineno}: {e.message}"


TEMPLATE_LIBRARY = {
    "slack": '{"text":"{{severity|severity_emoji}} {{title|truncate(100)}}"}',
    "teams": '{"@type":"MessageCard","summary":"{{title|truncate(100)}}"}',
    "generic": '{"event":"{{event}}","incident_id":"{{incident_id}}"}',
}


def get_template(name: str) -> str | None:
    return TEMPLATE_LIBRARY.get(name)


def list_templates() -> list[str]:
    return list(TEMPLATE_LIBRARY.keys())
