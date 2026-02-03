"""Data models for incident tagging system."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TagColor(str, Enum):
    """Predefined tag colors for UI consistency."""
    RED = "red"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    PURPLE = "purple"
    PINK = "pink"
    GRAY = "gray"
    TEAL = "teal"
    INDIGO = "indigo"


class Tag(BaseModel):
    """A tag that can be applied to incidents."""
    id: str = Field(..., description="Unique tag identifier")
    name: str = Field(..., min_length=1, max_length=50, description="Tag name")
    description: str | None = Field(None, max_length=255)
    color: TagColor = Field(default=TagColor.BLUE)
    parent_id: str | None = Field(None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None
    incident_count: int = Field(default=0)
    is_system: bool = Field(default=False)


class TagCreate(BaseModel):
    """Request to create a new tag."""
    name: str = Field(..., min_length=1, max_length=50)
    description: str | None = None
    color: TagColor = TagColor.BLUE
    parent_id: str | None = None


class TagUpdate(BaseModel):
    """Request to update an existing tag."""
    name: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = None
    color: TagColor | None = None
    parent_id: str | None = None


class IncidentTag(BaseModel):
    """Association between an incident and a tag."""
    incident_id: str
    tag_id: str
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    applied_by: str | None = None
    auto_applied: bool = False
    confidence: float | None = None


class AutoTagRuleType(str, Enum):
    """Types of auto-tagging rules."""
    SERVICE_NAME = "service_name"
    TITLE_KEYWORD = "title_keyword"
    SEVERITY = "severity"
    REGEX = "regex"


class AutoTagRule(BaseModel):
    """Rule for automatically applying tags to incidents."""
    id: str
    tag_id: str
    rule_type: AutoTagRuleType
    pattern: str
    is_enabled: bool = True
    priority: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None


class AutoTagRuleCreate(BaseModel):
    """Request to create an auto-tag rule."""
    tag_id: str
    rule_type: AutoTagRuleType
    pattern: str
    is_enabled: bool = True
    priority: int = 0


class AutoTagRuleUpdate(BaseModel):
    """Request to update an auto-tag rule."""
    pattern: str | None = None
    is_enabled: bool | None = None
    priority: int | None = None


class TagSuggestion(BaseModel):
    """An AI-suggested tag for an incident."""
    tag_id: str
    tag_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class TagHierarchy(BaseModel):
    """A tag with its children for hierarchical display."""
    tag: Tag
    children: list["TagHierarchy"] = Field(default_factory=list)


class TagStats(BaseModel):
    """Statistics for tag usage."""
    tag_id: str
    tag_name: str
    incident_count: int
    last_used: datetime | None = None
    avg_resolution_time_minutes: float | None = None


class IncidentTagsResponse(BaseModel):
    """Response containing incident's tags."""
    incident_id: str
    tags: list[Tag]


class AddTagsRequest(BaseModel):
    """Request to add tags to an incident."""
    tag_ids: list[str] = Field(..., min_length=1)


class TagIncidentsResponse(BaseModel):
    """Response containing tag's incidents."""
    tag: Tag
    incident_ids: list[str]
    total: int


class TagListResponse(BaseModel):
    """Response for listing tags."""
    tags: list[Tag]
    total: int


class TagSearchFilters(BaseModel):
    """Filters for searching incidents by tags."""
    tag_ids: list[str] | None = None
    include_children: bool = True
    match_all: bool = False
