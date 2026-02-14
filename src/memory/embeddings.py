"""Embedding providers for incident memory."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

import httpx
import structlog

from ..config import Settings
from .config import IncidentMemoryConfig

logger = structlog.get_logger()


class EmbeddingProvider(ABC):
    """Abstract provider interface for text embeddings."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate an embedding for text."""

    async def close(self) -> None:
        """Close provider resources."""


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embeddings provider."""

    def __init__(self, settings: Settings, config: IncidentMemoryConfig):
        self.settings = settings
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def embed(self, text: str) -> list[float]:
        if not self.settings.openai_api_key:
            logger.warning(
                "incident_memory_no_openai_api_key",
                provider="openai",
            )
            return [0.0] * self.config.embedding_dimensions

        client = await self._get_client()
        response = await client.post(
            "/embeddings",
            json={
                "model": self.config.embedding_model,
                "input": text,
            },
        )
        response.raise_for_status()
        payload = response.json()
        embedding = [float(value) for value in payload["data"][0]["embedding"]]
        return _fit_dimensions(embedding, self.config.embedding_dimensions)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client


class LocalEmbeddingProvider(EmbeddingProvider):
    """Local sentence-transformers embeddings provider."""

    def __init__(self, config: IncidentMemoryConfig):
        self.config = config
        self._model = None
        self._model_lock = asyncio.Lock()

    async def embed(self, text: str) -> list[float]:
        model = await self._get_model()
        if model is None:
            return [0.0] * self.config.embedding_dimensions

        vector = await asyncio.to_thread(
            model.encode,
            text,
            normalize_embeddings=self.config.local_embedding_normalize,
        )
        embedding = [float(value) for value in vector.tolist()]
        return _fit_dimensions(embedding, self.config.embedding_dimensions)

    async def _get_model(self):
        if self._model is not None:
            return self._model

        async with self._model_lock:
            if self._model is not None:
                return self._model

            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                logger.warning(
                    "incident_memory_local_embedding_unavailable",
                    reason="sentence_transformers_not_installed",
                )
                return None

            try:
                self._model = await asyncio.to_thread(
                    SentenceTransformer,
                    self.config.local_embedding_model,
                    device=self.config.local_embedding_device,
                )
                return self._model
            except Exception as exc:
                logger.warning(
                    "incident_memory_local_embedding_load_failed",
                    error=str(exc),
                    model=self.config.local_embedding_model,
                )
                return None


def build_embedding_provider(
    settings: Settings,
    config: IncidentMemoryConfig,
) -> EmbeddingProvider:
    """Build embedding provider from config."""
    provider = config.embedding_provider.lower().strip()
    if provider == "local":
        return LocalEmbeddingProvider(config=config)
    return OpenAIEmbeddingProvider(settings=settings, config=config)


def _fit_dimensions(embedding: list[float], dimensions: int) -> list[float]:
    if dimensions <= 0:
        return embedding
    if len(embedding) == dimensions:
        return embedding
    if len(embedding) > dimensions:
        return embedding[:dimensions]
    return embedding + ([0.0] * (dimensions - len(embedding)))
