"""Tests for the similarity search module."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from src.config import Settings
from src.models import PastIncident
from src.similarity.embeddings import EmbeddingGenerator, EMBEDDING_DIMENSION
from src.similarity.search import SimilaritySearch, cosine_similarity
from src.similarity.store import IncidentStore


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_incidents.db"


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(openai_api_key="test-key")


class TestCosineSimlarity:
    """Tests for cosine similarity calculation."""

    def test_identical_vectors(self):
        """Identical vectors should have similarity of 1."""
        v = np.array([1.0, 2.0, 3.0])
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity of 0."""
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0])
        assert cosine_similarity(v1, v2) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        """Opposite vectors should have similarity of -1."""
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([-1.0, 0.0, 0.0])
        assert cosine_similarity(v1, v2) == pytest.approx(-1.0)

    def test_zero_vector(self):
        """Zero vector should return 0."""
        v1 = np.array([0.0, 0.0, 0.0])
        v2 = np.array([1.0, 2.0, 3.0])
        assert cosine_similarity(v1, v2) == 0.0


class TestIncidentStore:
    """Tests for the incident store."""

    def test_store_and_retrieve(self, temp_db):
        """Test storing and retrieving an incident."""
        store = IncidentStore(temp_db)
        
        embedding = [0.1] * EMBEDDING_DIMENSION
        occurred = datetime(2024, 1, 15, 10, 0, 0)
        
        store.store_incident(
            incident_id="INC-001",
            title="Database connection timeout",
            service="payments-api",
            occurred_at=occurred,
            embedding=embedding,
            description="Connection pool exhausted",
        )
        
        incident = store.get_incident("INC-001")
        
        assert incident is not None
        assert incident.incident_id == "INC-001"
        assert incident.title == "Database connection timeout"
        assert incident.service == "payments-api"
        assert incident.description == "Connection pool exhausted"

    def test_update_resolution(self, temp_db):
        """Test updating resolution notes."""
        store = IncidentStore(temp_db)
        
        store.store_incident(
            incident_id="INC-002",
            title="Service outage",
            service="auth-service",
            occurred_at=datetime.utcnow(),
            embedding=[0.1] * EMBEDDING_DIMENSION,
        )
        
        updated = store.update_resolution(
            incident_id="INC-002",
            resolution="Restarted service and increased memory",
            root_cause="Memory leak in session handler",
        )
        
        assert updated is True
        
        incident = store.get_incident("INC-002")
        assert incident.resolution == "Restarted service and increased memory"
        assert incident.root_cause == "Memory leak in session handler"

    def test_get_all_with_embeddings(self, temp_db):
        """Test retrieving all incidents with embeddings."""
        store = IncidentStore(temp_db)
        
        # Store multiple incidents
        for i in range(3):
            store.store_incident(
                incident_id=f"INC-{i:03d}",
                title=f"Incident {i}",
                service="test-service",
                occurred_at=datetime.utcnow(),
                embedding=[float(i)] * EMBEDDING_DIMENSION,
            )
        
        results = store.get_all_with_embeddings()
        
        assert len(results) == 3
        for incident, embedding in results:
            assert isinstance(incident, PastIncident)
            assert isinstance(embedding, np.ndarray)
            assert len(embedding) == EMBEDDING_DIMENSION

    def test_count_incidents(self, temp_db):
        """Test counting incidents."""
        store = IncidentStore(temp_db)
        
        assert store.count_incidents() == 0
        
        store.store_incident(
            incident_id="INC-001",
            title="Test incident",
            service="test",
            occurred_at=datetime.utcnow(),
            embedding=[0.1] * EMBEDDING_DIMENSION,
        )
        
        assert store.count_incidents() == 1

    def test_get_recent_incidents(self, temp_db):
        """Test getting recent incidents with filters."""
        store = IncidentStore(temp_db)
        
        # Store incidents for different services
        for service in ["api", "api", "worker"]:
            store.store_incident(
                incident_id=f"INC-{service}-{datetime.utcnow().timestamp()}",
                title=f"{service} incident",
                service=service,
                occurred_at=datetime.utcnow(),
                embedding=[0.1] * EMBEDDING_DIMENSION,
            )
        
        all_incidents = store.get_recent_incidents(limit=10)
        assert len(all_incidents) == 3
        
        api_incidents = store.get_recent_incidents(limit=10, service="api")
        assert len(api_incidents) == 2


class TestEmbeddingGenerator:
    """Tests for embedding generation."""

    def test_prepare_incident_text(self, settings):
        """Test text preparation for embedding."""
        generator = EmbeddingGenerator(settings)
        
        text = generator._prepare_incident_text(
            title="Database timeout",
            service_name="payments-api",
            description="Connection pool exhausted",
            error_logs=["Error: timeout after 30s", "Connection refused"],
        )
        
        assert "Service: payments-api" in text
        assert "Title: Database timeout" in text
        assert "Description: Connection pool exhausted" in text
        assert "Error: timeout after 30s" in text

    def test_text_truncation(self, settings):
        """Test that long text is truncated."""
        generator = EmbeddingGenerator(settings)
        
        long_logs = ["x" * 1000 for _ in range(20)]
        text = generator._prepare_incident_text(
            title="Test",
            service_name="test",
            error_logs=long_logs,
        )
        
        # Should be truncated to ~8000 chars
        assert len(text) <= 8010

    @pytest.mark.asyncio
    async def test_generate_embedding_no_api_key(self):
        """Test graceful handling when no API key is set."""
        settings = Settings(openai_api_key="")
        generator = EmbeddingGenerator(settings)
        
        embedding = await generator.generate_embedding(
            title="Test incident",
            service_name="test-service",
        )
        
        # Should return zero vector when no API key
        assert len(embedding) == EMBEDDING_DIMENSION
        assert all(v == 0.0 for v in embedding)


class TestSimilaritySearch:
    """Tests for similarity search."""

    @pytest.mark.asyncio
    async def test_find_similar_no_incidents(self, temp_db, settings):
        """Test search when no past incidents exist."""
        store = IncidentStore(temp_db)
        search = SimilaritySearch(settings, store=store)
        
        with patch.object(search.embedder, 'generate_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * EMBEDDING_DIMENSION
            
            results = await search.find_similar(
                title="New incident",
                service_name="test-service",
            )
        
        assert results == []

    @pytest.mark.asyncio
    async def test_find_similar_basic(self, temp_db, settings):
        """Test finding similar incidents."""
        store = IncidentStore(temp_db)
        
        # Store some incidents with distinct embeddings
        # Incident 1: all 0.1
        store.store_incident(
            incident_id="INC-001",
            title="Database timeout",
            service="db-service",
            occurred_at=datetime.utcnow(),
            embedding=[0.1] * EMBEDDING_DIMENSION,
            resolution="Increased connection pool",
        )
        
        # Incident 2: all 0.9 (very different)
        store.store_incident(
            incident_id="INC-002",
            title="Memory leak",
            service="api-service",
            occurred_at=datetime.utcnow(),
            embedding=[0.9] * EMBEDDING_DIMENSION,
        )
        
        search = SimilaritySearch(settings, store=store)
        
        with patch.object(search.embedder, 'generate_embedding', new_callable=AsyncMock) as mock_embed:
            # Query embedding similar to INC-001
            mock_embed.return_value = [0.1] * EMBEDDING_DIMENSION
            
            results = await search.find_similar(
                title="Another DB issue",
                service_name="db-service",
                top_n=3,
                min_similarity=0.5,
            )
        
        assert len(results) >= 1
        # The most similar should be INC-001
        assert results[0].incident_id == "INC-001"
        assert results[0].similarity_score is not None
        assert results[0].resolution == "Increased connection pool"

    @pytest.mark.asyncio
    async def test_exclude_self(self, temp_db, settings):
        """Test that an incident doesn't match itself."""
        store = IncidentStore(temp_db)
        
        store.store_incident(
            incident_id="INC-001",
            title="Test incident",
            service="test",
            occurred_at=datetime.utcnow(),
            embedding=[0.1] * EMBEDDING_DIMENSION,
        )
        
        search = SimilaritySearch(settings, store=store)
        
        with patch.object(search.embedder, 'generate_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * EMBEDDING_DIMENSION
            
            results = await search.find_similar(
                title="Test incident",
                service_name="test",
                exclude_incident_id="INC-001",
            )
        
        # Should not find itself
        assert all(r.incident_id != "INC-001" for r in results)

    @pytest.mark.asyncio
    async def test_store_and_search(self, temp_db, settings):
        """Test combined store and search operation."""
        store = IncidentStore(temp_db)
        
        # Pre-populate with an incident
        store.store_incident(
            incident_id="INC-OLD",
            title="Old incident",
            service="test",
            occurred_at=datetime.utcnow(),
            embedding=[0.1] * EMBEDDING_DIMENSION,
            resolution="Fixed by restart",
        )
        
        search = SimilaritySearch(settings, store=store)
        
        with patch.object(search.embedder, 'generate_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * EMBEDDING_DIMENSION
            
            results = await search.store_and_search(
                incident_id="INC-NEW",
                title="New incident",
                service_name="test",
                occurred_at=datetime.utcnow(),
            )
        
        # Should find the old incident
        assert len(results) >= 1
        assert results[0].incident_id == "INC-OLD"
        
        # New incident should also be stored
        new_incident = store.get_incident("INC-NEW")
        assert new_incident is not None
        assert new_incident.title == "New incident"
