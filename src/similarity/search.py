"""Find similar past incidents using vector similarity."""

import numpy as np
import structlog

from ..config import Settings
from ..models import PastIncident
from .embeddings import EmbeddingGenerator
from .store import IncidentStore

logger = structlog.get_logger()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return float(np.dot(a, b) / (norm_a * norm_b))


class SimilaritySearch:
    """
    Search for similar past incidents using vector embeddings.
    
    Uses cosine similarity to find the most similar incidents based on
    their embedded representations of title, service, and error logs.
    """

    def __init__(
        self,
        settings: Settings,
        store: IncidentStore | None = None,
        embedding_generator: EmbeddingGenerator | None = None,
    ):
        self.settings = settings
        self.store = store or IncidentStore()
        self.embedder = embedding_generator or EmbeddingGenerator(settings)

    async def find_similar(
        self,
        title: str,
        service_name: str,
        description: str | None = None,
        error_logs: list[str] | None = None,
        top_n: int = 3,
        min_similarity: float = 0.5,
        exclude_incident_id: str | None = None,
    ) -> list[PastIncident]:
        """
        Find the most similar past incidents.
        
        Args:
            title: Current incident title
            service_name: Current service name
            description: Optional incident description
            error_logs: Optional list of error log messages
            top_n: Maximum number of similar incidents to return
            min_similarity: Minimum similarity score (0-1) to include
            exclude_incident_id: Incident ID to exclude from results (e.g., self)
            
        Returns:
            List of PastIncident objects with similarity_score set,
            ordered by similarity (highest first).
        """
        # Get all stored incidents with embeddings
        stored_incidents = self.store.get_all_with_embeddings()
        
        if not stored_incidents:
            logger.info("no_past_incidents_found")
            return []

        # Generate embedding for current incident
        try:
            query_embedding = await self.embedder.generate_embedding(
                title=title,
                service_name=service_name,
                description=description,
                error_logs=error_logs,
            )
            query_vector = np.array(query_embedding)
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            return []

        # Calculate similarity scores
        scored_incidents: list[tuple[PastIncident, float]] = []
        
        for incident, embedding in stored_incidents:
            # Skip the current incident if specified
            if exclude_incident_id and incident.incident_id == exclude_incident_id:
                continue
                
            similarity = cosine_similarity(query_vector, embedding)
            
            if similarity >= min_similarity:
                incident.similarity_score = round(similarity * 100, 1)  # Convert to percentage
                scored_incidents.append((incident, similarity))

        # Sort by similarity (highest first) and take top N
        scored_incidents.sort(key=lambda x: x[1], reverse=True)
        top_incidents = [incident for incident, _ in scored_incidents[:top_n]]

        logger.info(
            "similar_incidents_found",
            query_service=service_name,
            total_candidates=len(stored_incidents),
            matches_found=len(top_incidents),
        )

        return top_incidents

    async def find_similar_by_id(
        self,
        incident_id: str,
        top_n: int = 3,
        min_similarity: float = 0.5,
    ) -> list[PastIncident]:
        """
        Find similar incidents to a stored incident by its ID.
        
        Args:
            incident_id: ID of the incident to find similar ones for
            top_n: Maximum number of similar incidents to return
            min_similarity: Minimum similarity score to include
            
        Returns:
            List of similar PastIncident objects, or empty list if not found.
        """
        incident = self.store.get_incident(incident_id)
        
        if not incident:
            logger.warning("incident_not_found", incident_id=incident_id)
            return []

        return await self.find_similar(
            title=incident.title,
            service_name=incident.service,
            description=incident.description,
            top_n=top_n,
            min_similarity=min_similarity,
            exclude_incident_id=incident_id,
        )

    async def store_and_search(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        occurred_at,
        description: str | None = None,
        error_logs: list[str] | None = None,
        top_n: int = 3,
    ) -> list[PastIncident]:
        """
        Store a new incident and find similar past ones.
        
        This is the main entry point for processing new incidents.
        It generates the embedding, stores the incident, and returns
        similar past incidents.
        
        Args:
            incident_id: Unique incident identifier
            title: Incident title
            service_name: Service name
            occurred_at: When the incident occurred
            description: Optional description
            error_logs: Optional error log messages
            top_n: Number of similar incidents to return
            
        Returns:
            List of similar past incidents.
        """
        # First, find similar incidents BEFORE storing (so we don't match ourselves)
        similar = await self.find_similar(
            title=title,
            service_name=service_name,
            description=description,
            error_logs=error_logs,
            top_n=top_n,
            exclude_incident_id=incident_id,
        )

        # Generate embedding and store
        try:
            embedding = await self.embedder.generate_embedding(
                title=title,
                service_name=service_name,
                description=description,
                error_logs=error_logs,
            )
            
            self.store.store_incident(
                incident_id=incident_id,
                title=title,
                service=service_name,
                description=description,
                occurred_at=occurred_at,
                embedding=embedding,
            )
        except Exception as e:
            logger.error(
                "store_incident_failed",
                incident_id=incident_id,
                error=str(e),
            )
            # Still return similar incidents even if storage fails

        return similar

    async def close(self):
        """Clean up resources."""
        await self.embedder.close()
