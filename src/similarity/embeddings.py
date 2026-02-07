"""Generate embeddings using OpenAI API."""

import hashlib

import httpx
import structlog

from ..config import Settings

logger = structlog.get_logger()

# Default embedding model - good balance of quality and cost
DEFAULT_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536


class EmbeddingGenerator:
    """Generate vector embeddings for incident data using OpenAI API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.openai_api_key
        self.model = DEFAULT_MODEL
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _prepare_incident_text(
        self,
        title: str,
        service_name: str,
        description: str | None = None,
        error_logs: list[str] | None = None,
    ) -> str:
        """
        Prepare incident data as text for embedding.

        Combines title, service, description, and error logs into a single
        text representation that captures the incident's semantic meaning.
        """
        parts = [
            f"Service: {service_name}",
            f"Title: {title}",
        ]

        if description:
            parts.append(f"Description: {description}")

        if error_logs:
            # Include up to 10 unique error log entries (truncated)
            unique_logs = list(dict.fromkeys(error_logs))[:10]
            truncated_logs = [log[:500] for log in unique_logs]
            parts.append("Error logs:\n" + "\n".join(truncated_logs))

        text = "\n".join(parts)

        # Limit total text length to avoid token limits
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        return text

    async def generate_embedding(
        self,
        title: str,
        service_name: str,
        description: str | None = None,
        error_logs: list[str] | None = None,
    ) -> list[float]:
        """
        Generate embedding vector for incident data.

        Args:
            title: Incident title
            service_name: Name of the affected service
            description: Optional incident description
            error_logs: Optional list of error log messages

        Returns:
            List of floats representing the embedding vector
        """
        text = self._prepare_incident_text(title, service_name, description, error_logs)
        return await self._embed_text(text)

    async def _embed_text(self, text: str) -> list[float]:
        """Call OpenAI API to generate embedding."""
        if not self.api_key:
            logger.warning("openai_api_key_not_set", msg="Using zero vector for embedding")
            return [0.0] * EMBEDDING_DIMENSION

        client = await self._get_client()

        try:
            response = await client.post(
                "/embeddings",
                json={
                    "model": self.model,
                    "input": text,
                },
            )
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]

            logger.debug(
                "embedding_generated",
                text_length=len(text),
                embedding_dim=len(embedding),
            )

            return embedding

        except httpx.HTTPStatusError as e:
            logger.error(
                "openai_embedding_error",
                status_code=e.response.status_code,
                error=e.response.text,
            )
            raise
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            raise

    @staticmethod
    def text_hash(text: str) -> str:
        """Generate a hash for caching purposes."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
