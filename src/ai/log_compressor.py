"""
Log Compressor - Multi-stage pipeline to compress logs for LLM consumption.

Pipeline: Parse → Filter → Dedupe → Rank → Summarize

Reduces 100K+ log lines to <2K tokens of actionable insights.
"""

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger()


class LogLevel(Enum):
    FATAL = 5
    ERROR = 4
    WARN = 3
    INFO = 2
    DEBUG = 1
    TRACE = 0
    UNKNOWN = -1

    @classmethod
    def from_string(cls, s: str) -> "LogLevel":
        mapping = {
            "fatal": cls.FATAL, "critical": cls.FATAL, "crit": cls.FATAL,
            "error": cls.ERROR, "err": cls.ERROR, "severe": cls.ERROR,
            "warn": cls.WARN, "warning": cls.WARN,
            "info": cls.INFO, "notice": cls.INFO,
            "debug": cls.DEBUG,
            "trace": cls.TRACE, "verbose": cls.TRACE,
        }
        return mapping.get(s.lower().strip(), cls.UNKNOWN)


@dataclass
class LogEntry:
    """A single parsed log line."""
    timestamp: Optional[datetime]
    level: LogLevel
    service: str
    message: str
    raw: str


@dataclass
class LogPattern:
    """A deduplicated group of similar log entries."""
    signature: str
    canonical_message: str
    sample_raw: str
    count: int
    level: LogLevel
    services: set
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "signature": self.signature,
            "message": self.canonical_message[:500],
            "count": self.count,
            "level": self.level.name,
            "services": list(self.services),
            "score": round(self.score, 2),
        }


@dataclass
class CompressionStats:
    """Statistics about the compression process."""
    total_lines: int = 0
    parsed_lines: int = 0
    filtered_lines: int = 0
    unique_patterns: int = 0
    output_patterns: int = 0
    by_level: dict = field(default_factory=lambda: defaultdict(int))
    by_service: dict = field(default_factory=lambda: defaultdict(int))
    processing_time_ms: int = 0


@dataclass
class CompressedLogs:
    """Output of log compression."""
    patterns: list[LogPattern]
    stats: CompressionStats
    estimated_tokens: int = 0

    def to_context_string(self, max_patterns: int = 10) -> str:
        """Format for inclusion in LLM context."""
        lines = [
            f"## Log Analysis ({self.stats.filtered_lines} errors from {self.stats.total_lines} lines)",
            ""
        ]

        for i, p in enumerate(self.patterns[:max_patterns], 1):
            lines.append(f"{i}. [{p.level.name}] (x{p.count}) {p.canonical_message[:200]}")
            if len(p.services) > 1:
                lines.append(f"   Affected: {', '.join(list(p.services)[:5])}")

        return "\n".join(lines)


class LogParser:
    """Multi-format log parser with automatic format detection."""

    PATTERNS = [
        # ISO 8601: 2024-01-15T10:30:45.123Z [ERROR] [service] message
        (
            r'^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s*'
            r'\[?(?P<level>FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE)\]?\s*'
            r'(?:\[(?P<service>[\w.-]+)\])?\s*'
            r'(?P<msg>.+)$'
        ),
        # Simple: ERROR service: message
        (
            r'^(?:\[)?(?P<level>FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE)(?:\])?\s+'
            r'(?:(?P<service>[\w.-]+):\s+)?'
            r'(?P<msg>.+)$'
        ),
    ]

    ERROR_KEYWORDS = [
        'exception', 'error', 'failed', 'failure', 'fatal',
        'panic', 'crash', 'killed', 'oom', 'timeout',
    ]

    def __init__(self, default_service: str = "unknown"):
        self.default_service = default_service
        self._compiled = [(re.compile(p, re.IGNORECASE), p) for p in self.PATTERNS]

    def parse(self, line: str) -> Optional[LogEntry]:
        """Parse a single log line."""
        line = line.strip()
        if not line:
            return None

        # Try JSON first
        if line.startswith('{'):
            return self._parse_json(line)

        # Try regex patterns
        for pattern, _ in self._compiled:
            match = pattern.match(line)
            if match:
                groups = match.groupdict()
                return LogEntry(
                    timestamp=self._parse_timestamp(groups.get('ts')),
                    level=LogLevel.from_string(groups.get('level', '')),
                    service=groups.get('service') or self.default_service,
                    message=groups.get('msg', line),
                    raw=line,
                )

        # Fallback: check for error keywords
        line_lower = line.lower()
        if any(kw in line_lower for kw in self.ERROR_KEYWORDS):
            return LogEntry(
                timestamp=None,
                level=LogLevel.ERROR,
                service=self.default_service,
                message=line,
                raw=line,
            )

        return None

    def _parse_json(self, line: str) -> Optional[LogEntry]:
        """Parse JSON-formatted logs."""
        import json
        try:
            data = json.loads(line)
            level = LogLevel.UNKNOWN
            for f in ['level', 'severity', 'lvl']:
                if f in data:
                    level = LogLevel.from_string(str(data[f]))
                    if level != LogLevel.UNKNOWN:
                        break

            message = data.get('message') or data.get('msg') or data.get('error') or line
            service = data.get('service') or data.get('app') or self.default_service

            return LogEntry(
                timestamp=None,
                level=level,
                service=service,
                message=message,
                raw=line,
            )
        except json.JSONDecodeError:
            return None

    def _parse_timestamp(self, ts_str: Optional[str]) -> Optional[datetime]:
        if not ts_str:
            return None
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(ts_str.strip(), fmt)
            except ValueError:
                continue
        return None


class LogNormalizer:
    """Normalizes log messages for deduplication."""

    RULES = [
        (r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '<UUID>'),
        (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?\b', '<IP>'),
        (r'\b\d{13}\b', '<EPOCH_MS>'),
        (r'\b\d+(?:\.\d+)?(?:ms|s|m|h)\b', '<DURATION>'),
        (r':\d{4,5}\b', ':<PORT>'),
        (r'\bid[-=:]\s*\d+\b', 'id=<ID>'),
    ]

    def __init__(self):
        self._compiled = [(re.compile(p, re.IGNORECASE), r) for p, r in self.RULES]

    def normalize(self, message: str) -> tuple[str, str]:
        """Normalize message and return (normalized, signature)."""
        normalized = message
        for pattern, replacement in self._compiled:
            normalized = pattern.sub(replacement, normalized)
        normalized = ' '.join(normalized.lower().split())
        signature = hashlib.md5(normalized.encode()).hexdigest()[:16]
        return normalized, signature


class LogFilter:
    """Filters out noise from log entries."""

    NOISE_PATTERNS = [
        r'health[-_]?check', r'GET\s+/health', r'/ping', r'/metrics',
        r'kube-probe', r'readiness.*probe', r'liveness.*probe',
    ]

    def __init__(self, min_level: LogLevel = LogLevel.WARN):
        self.min_level = min_level
        self._noise = [re.compile(p, re.IGNORECASE) for p in self.NOISE_PATTERNS]

    def should_keep(self, entry: LogEntry) -> bool:
        if entry.level.value < self.min_level.value:
            return False
        for pattern in self._noise:
            if pattern.search(entry.message):
                return False
        return True


class PatternRanker:
    """Ranks log patterns by importance."""

    CRITICAL_KEYWORDS = [
        ('oom', 50), ('killed', 40), ('panic', 50), ('deadlock', 45),
        ('timeout', 20), ('connection refused', 25), ('circuit breaker', 30),
    ]

    def __init__(self, incident_time: Optional[datetime] = None):
        self.incident_time = incident_time or datetime.utcnow()
        self._keywords = [(re.compile(kw, re.IGNORECASE), boost) for kw, boost in self.CRITICAL_KEYWORDS]

    def score(self, pattern: LogPattern) -> float:
        score = 0.0

        # Severity
        severity_scores = {LogLevel.FATAL: 100, LogLevel.ERROR: 50, LogLevel.WARN: 10}
        score += severity_scores.get(pattern.level, 0)

        # Frequency (log scale)
        import math
        score += min(math.log10(pattern.count + 1) * 20, 100)

        # Recency
        if pattern.last_seen:
            age = self.incident_time - pattern.last_seen
            decay = 0.5 ** (age.total_seconds() / 900)  # 15-min half-life
            score += 50 * decay

        # Blast radius
        score += len(pattern.services) * 10

        # Keywords
        for kw_pattern, boost in self._keywords:
            if kw_pattern.search(pattern.canonical_message):
                score += boost

        pattern.score = score
        return score

    def rank(self, patterns: list[LogPattern], limit: int = 50) -> list[LogPattern]:
        for p in patterns:
            self.score(p)
        return sorted(patterns, key=lambda p: p.score, reverse=True)[:limit]


class LogCompressor:
    """
    Main log compression orchestrator.

    Usage:
        compressor = LogCompressor()
        result = compressor.compress(log_lines, service_name="payments-api")
        print(result.to_context_string())
    """

    def __init__(
        self,
        default_service: str = "unknown",
        min_level: LogLevel = LogLevel.WARN,
    ):
        self.parser = LogParser(default_service)
        self.normalizer = LogNormalizer()
        self.filter = LogFilter(min_level=min_level)
        self.ranker = PatternRanker()

    def compress(
        self,
        logs: list[str],
        service_name: str = "",
        incident_time: Optional[datetime] = None,
        max_patterns: int = 50,
    ) -> CompressedLogs:
        """Compress raw log lines into structured, ranked patterns."""
        import time
        start = time.time()

        if service_name:
            self.parser.default_service = service_name

        if incident_time:
            self.ranker.incident_time = incident_time

        stats = CompressionStats(total_lines=len(logs))

        # Stage 1: Parse
        entries = []
        for line in logs:
            entry = self.parser.parse(line)
            if entry:
                entries.append(entry)
        stats.parsed_lines = len(entries)

        # Stage 2: Filter
        filtered = [e for e in entries if self.filter.should_keep(e)]
        stats.filtered_lines = len(filtered)

        for e in filtered:
            stats.by_level[e.level.name] += 1
            stats.by_service[e.service] += 1

        # Stage 3: Deduplicate
        patterns = self._deduplicate(filtered)
        stats.unique_patterns = len(patterns)

        # Stage 4: Rank
        ranked = self.ranker.rank(patterns, limit=max_patterns)
        stats.output_patterns = len(ranked)

        stats.processing_time_ms = int((time.time() - start) * 1000)

        # Estimate tokens
        estimated_tokens = sum(len(p.canonical_message) for p in ranked) // 4

        return CompressedLogs(
            patterns=ranked,
            stats=stats,
            estimated_tokens=estimated_tokens,
        )

    def _deduplicate(self, entries: list[LogEntry]) -> list[LogPattern]:
        """Group similar entries into patterns."""
        patterns: dict[str, LogPattern] = {}

        for entry in entries:
            template, signature = self.normalizer.normalize(entry.message)

            if signature in patterns:
                p = patterns[signature]
                p.count += 1
                if entry.timestamp:
                    if p.last_seen is None or entry.timestamp > p.last_seen:
                        p.last_seen = entry.timestamp
                    if p.first_seen is None or entry.timestamp < p.first_seen:
                        p.first_seen = entry.timestamp
                p.services.add(entry.service)
            else:
                patterns[signature] = LogPattern(
                    signature=signature,
                    canonical_message=template,
                    sample_raw=entry.raw,
                    count=1,
                    level=entry.level,
                    services={entry.service},
                    first_seen=entry.timestamp,
                    last_seen=entry.timestamp,
                )

        return list(patterns.values())
