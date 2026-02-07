"""Data models for alert correlation."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CorrelationStrategy(StrEnum):
    TIME_BASED = "time_based"
    SERVICE_BASED = "service"
    TAG_BASED = "tag"
    PATTERN_BASED = "pattern"
    COMPOSITE = "composite"


class AlertGroupStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    CLOSED = "closed"
    RESOLVED = "resolved"


class IncomingAlert(BaseModel):
    alert_id: str
    source: str
    title: str
    description: str | None = None
    service: str
    severity: str = "medium"
    tags: list[str] = Field(default_factory=list)
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
    url: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AlertGroup(BaseModel):
    group_id: str
    rule_id: str | None = None
    strategy: CorrelationStrategy
    status: AlertGroupStatus = AlertGroupStatus.ACTIVE
    fingerprint: str
    alert_ids: list[str] = Field(default_factory=list)
    alert_count: int = 0
    representative_alert: IncomingAlert | None = None
    service: str | None = None
    services: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    first_alert_at: datetime | None = None
    last_alert_at: datetime | None = None
    window_expires_at: datetime | None = None
    notification_sent: bool = False
    suppressed_count: int = 0
    title: str | None = None
    summary: str | None = None

    def add_alert(self, alert: IncomingAlert) -> None:
        if alert.alert_id not in self.alert_ids:
            self.alert_ids.append(alert.alert_id)
        self.alert_count = len(self.alert_ids)
        if alert.service and alert.service not in self.services:
            self.services.append(alert.service)
        for tag in alert.tags:
            if tag not in self.tags:
                self.tags.append(tag)
        self.last_alert_at = alert.triggered_at
        self.updated_at = datetime.utcnow()
        if not self.first_alert_at:
            self.first_alert_at = alert.triggered_at
        if not self.representative_alert:
            self.representative_alert = alert
            self.service = alert.service
            self.title = f"[{alert.service}] {alert.title}"

    def update_summary(self) -> None:
        parts = [f"{self.alert_count} related alerts" if self.alert_count > 1 else "1 alert"]
        if len(self.services) > 1:
            parts.append(f"across {len(self.services)} services")
        elif self.service:
            parts.append(f"in {self.service}")
        if self.suppressed_count > 0:
            parts.append(f"({self.suppressed_count} notifications suppressed)")
        self.summary = " ".join(parts)


class CorrelationRule(BaseModel):
    rule_id: str
    name: str
    description: str | None = None
    strategy: CorrelationStrategy
    enabled: bool = True
    priority: int = 0
    time_window_seconds: int = Field(default=300, ge=30, le=3600)
    services: list[str] = Field(default_factory=list)
    match_tags: list[str] = Field(default_factory=list)
    group_by_tags: list[str] = Field(default_factory=list)
    title_patterns: list[str] = Field(default_factory=list)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    sub_strategies: list[CorrelationStrategy] = Field(default_factory=list)
    require_all: bool = True
    suppress_duplicates: bool = True
    max_alerts_before_notify: int = 1
    re_notify_after_seconds: int = 1800
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None

    def matches_service(self, service: str) -> bool:
        return not self.services or service in self.services

    def matches_tags(self, alert_tags: list[str]) -> bool:
        return not self.match_tags or all(tag in alert_tags for tag in self.match_tags)


class CorrelationResult(BaseModel):
    alert: IncomingAlert
    correlated: bool
    group: AlertGroup | None = None
    new_group: bool = False
    rule_matched: CorrelationRule | None = None
    should_notify: bool = True
    suppression_reason: str | None = None
