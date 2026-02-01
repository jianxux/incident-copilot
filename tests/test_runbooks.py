"""Tests for runbook auto-linking."""

import pytest

from src.runbooks import RunbookLinker
from src.runbooks.indexer import RunbookIndexer
from src.runbooks.models import Runbook, RunbookIndex, RunbookSource, RunbookSourceType


class TestRunbookIndexer:
    """Tests for RunbookIndexer."""

    def test_extract_keywords(self):
        """Test keyword extraction from text."""
        indexer = RunbookIndexer()

        text = "The payments service is experiencing high CPU usage. Check the database connections."
        keywords = indexer._extract_keywords(text)

        assert "payments" in keywords
        assert "service" in keywords
        assert "cpu" in keywords
        assert "database" in keywords
        assert "connections" in keywords
        # Stopwords should be filtered
        assert "the" not in keywords
        assert "is" not in keywords

    def test_extract_tags_from_frontmatter(self):
        """Test tag extraction from markdown frontmatter."""
        indexer = RunbookIndexer()

        content = """---
title: Database Troubleshooting
tags: [database, mysql, troubleshooting]
---

# Database Troubleshooting

Steps to troubleshoot database issues.
"""
        tags = indexer._extract_tags(content)

        assert "database" in tags
        assert "mysql" in tags
        assert "troubleshooting" in tags

    def test_extract_services(self):
        """Test service name extraction."""
        indexer = RunbookIndexer()

        content = """
## Service: payments-api

This runbook covers the payments-api service.

services: [payments-api, checkout-service]
"""
        services = indexer._extract_services(content)

        assert "payments-api" in services

    def test_parse_markdown_runbook(self):
        """Test markdown runbook parsing."""
        indexer = RunbookIndexer()
        source = RunbookSource(
            type=RunbookSourceType.LOCAL,
            name="test",
            local_path="/tmp/test",
        )

        content = """# High CPU Troubleshooting

This runbook helps diagnose high CPU issues.

## Steps

1. Check top processes
2. Review application logs
"""

        runbook = indexer._parse_markdown_runbook(
            content=content,
            filename="high-cpu.md",
            url="https://example.com/high-cpu.md",
            source=source,
        )

        assert runbook.title == "High CPU Troubleshooting"
        assert "cpu" in runbook.keywords
        assert "troubleshooting" in runbook.keywords
        assert runbook.url == "https://example.com/high-cpu.md"


class TestRunbookLinker:
    """Tests for RunbookLinker."""

    @pytest.fixture
    def sample_index(self):
        """Create a sample runbook index."""
        runbooks = [
            Runbook(
                id="rb-1",
                title="High CPU Troubleshooting",
                url="https://docs.example.com/cpu",
                source_type=RunbookSourceType.GITHUB,
                source_name="main-docs",
                content="Steps to troubleshoot high CPU usage on production servers.",
                keywords=["cpu", "high", "troubleshooting", "production", "servers"],
                services=["payments-api", "checkout-service"],
            ),
            Runbook(
                id="rb-2",
                title="Database Connection Issues",
                url="https://docs.example.com/db",
                source_type=RunbookSourceType.GITHUB,
                source_name="main-docs",
                content="How to fix database connection pool exhaustion.",
                keywords=["database", "connection", "pool", "exhaustion", "mysql"],
                services=["user-service"],
            ),
            Runbook(
                id="rb-3",
                title="Memory Leak Investigation",
                url="https://docs.example.com/memory",
                source_type=RunbookSourceType.NOTION,
                source_name="notion-docs",
                content="Steps to identify and fix memory leaks in Java applications.",
                keywords=["memory", "leak", "java", "heap", "investigation"],
                services=["payments-api"],
            ),
        ]

        vocabulary = {
            "cpu": 1,
            "high": 1,
            "troubleshooting": 1,
            "database": 1,
            "connection": 1,
            "memory": 1,
            "leak": 1,
            "payments-api": 2,
        }

        return RunbookIndex(runbooks=runbooks, vocabulary=vocabulary)

    def test_find_relevant_runbooks_by_query(self, sample_index):
        """Test finding runbooks by query text."""
        linker = RunbookLinker()
        linker._index = sample_index
        linker._compute_idf()

        matches = linker.find_relevant_runbooks(
            query="high CPU usage on server",
            top_k=3,
        )

        assert len(matches) > 0
        # First match should be the CPU runbook
        assert matches[0].title == "High CPU Troubleshooting"
        assert matches[0].relevance_score > 0

    def test_find_relevant_runbooks_with_service_boost(self, sample_index):
        """Test that service name provides a relevance boost."""
        linker = RunbookLinker()
        linker._index = sample_index
        linker._compute_idf()

        # Query about memory with payments-api service
        matches = linker.find_relevant_runbooks(
            query="memory issues",
            service_name="payments-api",
            top_k=3,
        )

        assert len(matches) > 0
        # Memory leak runbook should match (it's for payments-api)
        titles = [m.title for m in matches]
        assert "Memory Leak Investigation" in titles

    def test_search_api(self, sample_index):
        """Test the simple search API."""
        linker = RunbookLinker()
        linker._index = sample_index
        linker._compute_idf()

        matches = linker.search("database connection", top_k=5)

        assert len(matches) > 0
        assert any("Database" in m.title for m in matches)

    def test_min_score_filtering(self, sample_index):
        """Test that low-scoring results are filtered."""
        linker = RunbookLinker()
        linker._index = sample_index
        linker._compute_idf()

        # Query with unrelated terms
        matches = linker.find_relevant_runbooks(
            query="kubernetes network policy",
            min_score=0.5,
            top_k=10,
        )

        # Should return no or few results due to high min_score
        for match in matches:
            assert match.relevance_score >= 0.5
