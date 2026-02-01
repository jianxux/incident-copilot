"""Prometheus metrics endpoint."""

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    generate_latest,
    CollectorRegistry,
    REGISTRY,
    multiprocess,
    GC_COLLECTOR,
    PLATFORM_COLLECTOR,
    PROCESS_COLLECTOR,
)
import os

router = APIRouter(tags=["metrics"])


def get_metrics_registry() -> CollectorRegistry:
    """Get the appropriate metrics registry.
    
    Handles both single-process and multi-process (gunicorn) deployments.
    """
    # Check if running in multiprocess mode (e.g., gunicorn with workers)
    prometheus_multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    
    if prometheus_multiproc_dir:
        # Multiprocess mode - aggregate metrics from all workers
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    
    # Single process mode - use default registry
    return REGISTRY


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus metrics",
    description="Returns metrics in Prometheus exposition format",
    responses={
        200: {
            "content": {"text/plain": {}},
            "description": "Prometheus metrics in text format",
        }
    },
)
async def metrics(request: Request) -> Response:
    """Expose Prometheus metrics endpoint.
    
    This endpoint is designed to be scraped by Prometheus.
    Metrics include:
    - Webhook request counts and latencies
    - Context assembly times
    - Integration API call metrics
    - AI/LLM usage metrics
    - HTTP request metrics
    """
    registry = get_metrics_registry()
    
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get(
    "/metrics/health",
    summary="Metrics health check",
    description="Check if metrics collection is working",
)
async def metrics_health() -> dict:
    """Health check for metrics collection."""
    prometheus_multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    
    return {
        "status": "ok",
        "multiprocess_mode": prometheus_multiproc_dir is not None,
        "multiprocess_dir": prometheus_multiproc_dir,
    }
