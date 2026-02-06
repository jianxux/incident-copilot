"""Data models for runbook auto-linking."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RunbookSourceType(StrEnum):
    """Types of runbook sources."""

    GITHUB = "github"
    NOTION = "notion"
    CONFLUENCE = "confluence"
    LOCAL = "local"


class RunbookSource(BaseModel):
    """Configuration for a runbook source."""

    type: RunbookSourceType
    name: str
    enabled: bool = True

    # GitHub-specific
    repo: str | None = None
    branch: str = "main"
    paths: list[str] = Field(default_factory=lambda: ["docs/runbooks"])

    # Notion-specific
    notion_token: str | None = None
    notion_database_id: str | None = None

    # Confluence-specific
    confluence_url: str | None = None
    confluence_space: str | None = None

    # Local-specific
    local_path: str | None = None
    base_url: str | None = None  # URL prefix for linking


class Runbook(BaseModel):
    """A runbook document."""

    id: str
    title: str
    url: str
    source_type: RunbookSourceType
    source_name: str

    # Content for indexing
    content: str = ""
    description: str | None = None

    # Extracted metadata
    keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)  # Associated services

    # Indexing metadata
    indexed_at: datetime = Field(default_factory=datetime.utcnow)
    content_hash: str | None = None


class RunbookMatch(BaseModel):
    """A runbook matched to an incident."""

    runbook_id: str
    title: str
    url: str
    source_type: RunbookSourceType
    source_name: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    matched_terms: list[str] = Field(default_factory=list)
    description: str | None = None


class RunbookIndex(BaseModel):
    """Serialized runbook index."""

    version: str = "1.0"
    built_at: datetime = Field(default_factory=datetime.utcnow)
    runbooks: list[Runbook] = Field(default_factory=list)
    vocabulary: dict[str, int] = Field(default_factory=dict)  # term -> doc frequency
