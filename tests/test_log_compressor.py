"""Unit tests for the log compressor."""

from datetime import datetime

from src.ai.log_compressor import (
    LogCompressor,
    LogEntry,
    LogFilter,
    LogLevel,
    LogNormalizer,
    LogParser,
    LogPattern,
    PatternRanker,
)


class TestLogParser:
    """Tests for LogParser."""

    def test_parse_iso_format(self):
        """Test parsing ISO 8601 timestamp format."""
        parser = LogParser(default_service="test")
        entry = parser.parse(
            "2024-01-15T10:30:45.123Z [ERROR] [payments-api] Connection timeout"
        )

        assert entry is not None
        assert entry.level == LogLevel.ERROR
        assert entry.service == "payments-api"
        assert "Connection timeout" in entry.message

    def test_parse_simple_format(self):
        """Test parsing simple ERROR prefix format."""
        parser = LogParser(default_service="test")
        entry = parser.parse("ERROR user-service: Failed to authenticate")

        assert entry is not None
        assert entry.level == LogLevel.ERROR
        assert entry.service == "user-service"
        assert "Failed to authenticate" in entry.message

    def test_parse_json_format(self):
        """Test parsing JSON log format."""
        parser = LogParser(default_service="test")
        entry = parser.parse(
            '{"level": "error", "message": "Database connection failed", "service": "db-proxy"}'
        )

        assert entry is not None
        assert entry.level == LogLevel.ERROR
        assert entry.service == "db-proxy"
        assert "Database connection failed" in entry.message

    def test_parse_fallback_with_error_keyword(self):
        """Test fallback parsing when error keywords present."""
        parser = LogParser(default_service="fallback-svc")
        entry = parser.parse("Something failed with an exception in the system")

        assert entry is not None
        assert entry.level == LogLevel.ERROR
        assert entry.service == "fallback-svc"

    def test_parse_returns_none_for_non_error(self):
        """Test that non-error lines without format return None."""
        parser = LogParser()
        entry = parser.parse("Just a regular info message")

        assert entry is None

    def test_parse_empty_line(self):
        """Test parsing empty lines."""
        parser = LogParser()
        assert parser.parse("") is None
        assert parser.parse("   ") is None

    def test_parse_warn_level(self):
        """Test parsing WARN level logs."""
        parser = LogParser()
        entry = parser.parse("2024-01-15T10:30:45Z [WARN] [api] High latency detected")

        assert entry is not None
        assert entry.level == LogLevel.WARN

    def test_parse_fatal_level(self):
        """Test parsing FATAL level logs."""
        parser = LogParser()
        entry = parser.parse("FATAL app: Process killed by OOM")

        assert entry is not None
        assert entry.level == LogLevel.FATAL


class TestLogNormalizer:
    """Tests for LogNormalizer."""

    def test_normalize_uuid(self):
        """Test UUID normalization."""
        normalizer = LogNormalizer()
        normalized, sig = normalizer.normalize(
            "Request 550e8400-e29b-41d4-a716-446655440000 failed"
        )

        assert "<UUID>" in normalized.upper() or "<uuid>" in normalized

    def test_normalize_ip_address(self):
        """Test IP address normalization."""
        normalizer = LogNormalizer()
        normalized, sig = normalizer.normalize(
            "Connection to 192.168.1.100:5432 refused"
        )

        assert "<IP>" in normalized.upper() or "<ip>" in normalized

    def test_normalize_duration(self):
        """Test duration normalization."""
        normalizer = LogNormalizer()
        normalized, sig = normalizer.normalize("Request took 1500ms to complete")

        assert "<DURATION>" in normalized.upper() or "<duration>" in normalized

    def test_same_signature_for_similar_messages(self):
        """Test that similar messages get same signature."""
        normalizer = LogNormalizer()

        _, sig1 = normalizer.normalize(
            "Connection to 10.0.0.1:5432 timed out after 30000ms"
        )
        _, sig2 = normalizer.normalize(
            "Connection to 10.0.0.2:5432 timed out after 25000ms"
        )

        assert sig1 == sig2

    def test_different_signature_for_different_messages(self):
        """Test that different messages get different signatures."""
        normalizer = LogNormalizer()

        _, sig1 = normalizer.normalize("Connection timeout to database")
        _, sig2 = normalizer.normalize("Authentication failed for user")

        assert sig1 != sig2


class TestLogFilter:
    """Tests for LogFilter."""

    def test_filter_keeps_errors(self):
        """Test that ERROR level logs are kept."""
        filter = LogFilter(min_level=LogLevel.WARN)
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=LogLevel.ERROR,
            service="test",
            message="An error occurred",
            raw="ERROR test: An error occurred",
        )

        assert filter.should_keep(entry) is True

    def test_filter_removes_debug(self):
        """Test that DEBUG level logs are filtered."""
        filter = LogFilter(min_level=LogLevel.WARN)
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=LogLevel.DEBUG,
            service="test",
            message="Debug message",
            raw="DEBUG test: Debug message",
        )

        assert filter.should_keep(entry) is False

    def test_filter_removes_health_checks(self):
        """Test that health check logs are filtered."""
        filter = LogFilter(min_level=LogLevel.WARN)
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=LogLevel.ERROR,  # Even errors with health check patterns
            service="test",
            message="GET /health returned 200",
            raw="ERROR test: GET /health returned 200",
        )

        assert filter.should_keep(entry) is False

    def test_filter_removes_metrics_endpoint(self):
        """Test that /metrics endpoint logs are filtered."""
        filter = LogFilter(min_level=LogLevel.WARN)
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=LogLevel.ERROR,
            service="test",
            message="Prometheus scrape /metrics",
            raw="ERROR test: Prometheus scrape /metrics",
        )

        assert filter.should_keep(entry) is False


class TestPatternRanker:
    """Tests for PatternRanker."""

    def test_fatal_ranked_higher_than_error(self):
        """Test that FATAL patterns score higher than ERROR."""
        ranker = PatternRanker()

        fatal_pattern = LogPattern(
            signature="fatal1",
            canonical_message="Process killed",
            sample_raw="FATAL: Process killed",
            count=1,
            level=LogLevel.FATAL,
            services={"svc1"},
        )

        error_pattern = LogPattern(
            signature="error1",
            canonical_message="Connection failed",
            sample_raw="ERROR: Connection failed",
            count=1,
            level=LogLevel.ERROR,
            services={"svc1"},
        )

        fatal_score = ranker.score(fatal_pattern)
        error_score = ranker.score(error_pattern)

        assert fatal_score > error_score

    def test_higher_count_higher_score(self):
        """Test that more frequent patterns score higher."""
        ranker = PatternRanker()

        frequent = LogPattern(
            signature="freq1",
            canonical_message="Error X",
            sample_raw="ERROR: Error X",
            count=100,
            level=LogLevel.ERROR,
            services={"svc1"},
        )

        rare = LogPattern(
            signature="rare1",
            canonical_message="Error Y",
            sample_raw="ERROR: Error Y",
            count=1,
            level=LogLevel.ERROR,
            services={"svc1"},
        )

        freq_score = ranker.score(frequent)
        rare_score = ranker.score(rare)

        assert freq_score > rare_score

    def test_blast_radius_increases_score(self):
        """Test that patterns affecting multiple services score higher."""
        ranker = PatternRanker()

        multi_service = LogPattern(
            signature="multi1",
            canonical_message="Shared error",
            sample_raw="ERROR: Shared error",
            count=10,
            level=LogLevel.ERROR,
            services={"svc1", "svc2", "svc3", "svc4"},
        )

        single_service = LogPattern(
            signature="single1",
            canonical_message="Local error",
            sample_raw="ERROR: Local error",
            count=10,
            level=LogLevel.ERROR,
            services={"svc1"},
        )

        multi_score = ranker.score(multi_service)
        single_score = ranker.score(single_service)

        assert multi_score > single_score

    def test_oom_keyword_boosts_score(self):
        """Test that OOM keyword boosts score."""
        ranker = PatternRanker()

        oom = LogPattern(
            signature="oom1",
            canonical_message="Container killed by OOM",
            sample_raw="ERROR: Container killed by OOM",
            count=1,
            level=LogLevel.ERROR,
            services={"svc1"},
        )

        normal = LogPattern(
            signature="normal1",
            canonical_message="Request failed",
            sample_raw="ERROR: Request failed",
            count=1,
            level=LogLevel.ERROR,
            services={"svc1"},
        )

        oom_score = ranker.score(oom)
        normal_score = ranker.score(normal)

        assert oom_score > normal_score

    def test_rank_returns_limited_patterns(self):
        """Test that rank respects limit parameter."""
        ranker = PatternRanker()
        patterns = [
            LogPattern(
                signature=f"sig{i}",
                canonical_message=f"Error {i}",
                sample_raw=f"ERROR: Error {i}",
                count=i,
                level=LogLevel.ERROR,
                services={"svc1"},
            )
            for i in range(100)
        ]

        ranked = ranker.rank(patterns, limit=10)

        assert len(ranked) == 10


class TestLogCompressor:
    """Integration tests for LogCompressor."""

    def test_compress_deduplicates_similar_logs(self):
        """Test that similar logs are deduplicated."""
        compressor = LogCompressor()
        logs = [
            "2024-01-15T10:30:45Z [ERROR] [api] Connection to 10.0.0.1 failed",
            "2024-01-15T10:30:46Z [ERROR] [api] Connection to 10.0.0.2 failed",
            "2024-01-15T10:30:47Z [ERROR] [api] Connection to 10.0.0.3 failed",
            "2024-01-15T10:30:48Z [ERROR] [api] Connection to 10.0.0.4 failed",
        ]

        result = compressor.compress(logs, "api")

        assert result.stats.total_lines == 4
        assert result.stats.output_patterns == 1
        assert result.patterns[0].count == 4

    def test_compress_filters_noise(self):
        """Test that health checks are filtered out."""
        compressor = LogCompressor()
        logs = [
            "2024-01-15T10:30:45Z [ERROR] [api] Real error occurred",
            "2024-01-15T10:30:46Z [INFO] [api] GET /health 200",
            "2024-01-15T10:30:47Z [INFO] [api] GET /health 200",
            "2024-01-15T10:30:48Z [INFO] [api] GET /ping 200",
        ]

        result = compressor.compress(logs, "api")

        assert result.stats.total_lines == 4
        assert result.stats.filtered_lines == 1  # Only the real error

    def test_compress_ranks_by_severity(self):
        """Test that patterns are ranked by severity."""
        compressor = LogCompressor()
        logs = [
            "2024-01-15T10:30:45Z [WARN] [api] Warning message",
            "2024-01-15T10:30:46Z [ERROR] [api] Error message",
            "2024-01-15T10:30:47Z [FATAL] [api] Fatal message",
        ]

        result = compressor.compress(logs, "api")

        assert result.patterns[0].level == LogLevel.FATAL
        assert result.patterns[1].level == LogLevel.ERROR

    def test_compress_empty_logs(self):
        """Test compressing empty log list."""
        compressor = LogCompressor()
        result = compressor.compress([], "api")

        assert result.stats.total_lines == 0
        assert result.stats.output_patterns == 0
        assert len(result.patterns) == 0

    def test_compress_stats_accuracy(self):
        """Test that compression stats are accurate."""
        compressor = LogCompressor()
        logs = [
            "2024-01-15T10:30:45Z [ERROR] [api] Error type A",
            "2024-01-15T10:30:46Z [ERROR] [api] Error type A",
            "2024-01-15T10:30:47Z [ERROR] [api] Error type B",
            "2024-01-15T10:30:48Z [WARN] [api] Warning type C",
            "2024-01-15T10:30:49Z [INFO] [api] Info message",  # Filtered
        ]

        result = compressor.compress(logs, "api")

        assert result.stats.total_lines == 5
        assert result.stats.parsed_lines == 5
        assert result.stats.filtered_lines == 4  # INFO filtered
        assert result.stats.unique_patterns == 3
        assert result.stats.by_level["ERROR"] == 3
        assert result.stats.by_level["WARN"] == 1

    def test_to_context_string(self):
        """Test context string generation."""
        compressor = LogCompressor()
        logs = [
            "2024-01-15T10:30:45Z [ERROR] [api] Connection timeout to database",
            "2024-01-15T10:30:46Z [ERROR] [api] Connection timeout to database",
        ]

        result = compressor.compress(logs, "api")
        context = result.to_context_string()

        assert "Log Analysis" in context
        assert "ERROR" in context
        assert "x2" in context or "(x2)" in context

    def test_compress_large_batch(self):
        """Test compressing a large batch of logs efficiently."""
        compressor = LogCompressor()

        # Generate 1000 logs - test that processing is fast
        patterns = [
            "Connection timeout to database",
            "Failed to authenticate user",
            "Memory allocation failed",
            "Disk space low",
            "Network unreachable",
        ]
        logs = []
        for i in range(1000):
            pattern = patterns[i % len(patterns)]
            # Add varying IPs to create realistic logs that will deduplicate
            logs.append(
                f"2024-01-15T10:30:{i % 60:02d}Z [ERROR] [api] {pattern} from 10.0.{i // 256}.{i % 256}"
            )

        result = compressor.compress(logs, "api")

        assert result.stats.total_lines == 1000
        # Should deduplicate to ~5 patterns (one per pattern type)
        assert result.stats.unique_patterns <= 10  # Allow some variance
        assert result.stats.processing_time_ms < 5000  # Should be fast

    def test_compress_preserves_sample(self):
        """Test that sample_raw is preserved in patterns."""
        compressor = LogCompressor()
        logs = ["2024-01-15T10:30:45Z [ERROR] [api] Unique error message here"]

        result = compressor.compress(logs, "api")

        assert result.patterns[0].sample_raw == logs[0]
