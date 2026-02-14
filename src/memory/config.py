"""Configuration for incident memory capture and recall."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..config import Settings


class IncidentMemoryConfig(BaseSettings):
    """Memory feature flags and tuning parameters."""

    model_config = SettingsConfigDict(
        env_prefix="incident_memory_",
        extra="ignore",
    )

    enabled: bool = Field(default=True)

    # Storage
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/incident_copilot"
    )
    table_name: str = Field(default="incident_memory")

    # Embeddings
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int = Field(default=1536)

    # Capture pipeline
    capture_model: str = Field(default="claude-3-haiku-20240307")
    capture_max_tokens: int = Field(default=1200)
    capture_temperature: float = Field(default=0.0)

    # Recall pipeline
    recall_default_limit: int = Field(default=5)
    recall_candidate_limit: int = Field(default=50)
    recall_min_similarity: float = Field(default=0.15)
    recall_temporal_half_life_days: int = Field(default=30)
    recall_temporal_decay_rate: float = Field(default=0.95)
    recall_temporal_decay_window_days: int = Field(default=30)
    recall_service_boost: float = Field(default=0.08)
    recall_severity_boost: float = Field(default=0.05)

    # Feedback storage
    feedback_database_path: str = Field(default="data/incident_memory_feedback.db")

    # Claude rerank for high-severity contexts
    recall_enable_rerank: bool = Field(default=True)
    recall_rerank_model: str = Field(default="claude-3-haiku-20240307")
    recall_rerank_max_tokens: int = Field(default=800)
    recall_rerank_severity_threshold: str = Field(default="high")

    # Migration/index tuning
    ivfflat_lists: int = Field(default=100)

    @classmethod
    def from_settings(cls, settings: Settings) -> "IncidentMemoryConfig":
        """Derive memory config from global app settings."""
        return cls(
            database_url=settings.database_url,
            capture_model=settings.ai_model,
        )
