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
    embedding_provider: str = Field(default="openai")
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int = Field(default=1536)
    local_embedding_model: str = Field(default="all-MiniLM-L6-v2")
    local_embedding_device: str = Field(default="cpu")
    local_embedding_normalize: bool = Field(default=True)

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
    use_hnsw_index: bool = Field(default=False)
    hnsw_m: int = Field(default=16)
    hnsw_ef_construction: int = Field(default=64)

    # Correlation
    correlations_table_name: str = Field(default="service_correlations")
    correlation_min_cooccurrence: int = Field(default=2)
    correlation_rebuild_interval_seconds: int = Field(default=1800)
    correlation_lookback_days: int = Field(default=180)
    correlation_max_pairs: int = Field(default=1000)

    # Auto-runbooks
    runbooks_table_name: str = Field(default="generated_runbooks")
    runbook_min_occurrences: int = Field(default=2)
    runbook_max_groups: int = Field(default=100)
    runbook_synthesis_model: str = Field(default="claude-3-haiku-20240307")
    runbook_synthesis_max_tokens: int = Field(default=900)
    runbook_rebuild_interval_seconds: int = Field(default=3600)

    # Health
    health_snapshots_table_name: str = Field(default="memory_health_snapshots")
    health_metrics_database_path: str = Field(default="data/incident_memory_health.db")
    health_stale_record_days: int = Field(default=90)

    @classmethod
    def from_settings(cls, settings: Settings) -> "IncidentMemoryConfig":
        """Derive memory config from global app settings."""
        return cls(
            database_url=settings.database_url,
            capture_model=settings.ai_model,
        )
