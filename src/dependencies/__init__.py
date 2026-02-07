"""Service Dependencies module for incident-copilot.

This module provides service dependency mapping, blast radius calculation,
and auto-discovery from distributed tracing.

Usage:
    from dependencies import (
        DependencyService,
        get_dependency_service,
        router,
    )
    
    # Add routes to FastAPI app
    app.include_router(router)
    
    # Use service directly
    service = get_dependency_service()
    blast = await service.calculate_blast_radius("payment-service")
"""

from .discovery import DependencyDiscovery
from .graph import DependencyGraphAnalyzer
from .models import (
    BlastRadius,
    CriticalityLevel,
    CycleInfo,
    Dependency,
    DependencyCreate,
    DependencyGraph,
    DependencyPath,
    DependencyType,
    GraphStats,
    HealthStatus,
    Service,
    ServiceCreate,
    TraceSpan,
)
from .routes import router
from .service import DependencyService, get_dependency_service
from .visualization import GraphVisualizer

__all__ = [
    # Models
    "BlastRadius",
    "CriticalityLevel",
    "CycleInfo",
    "Dependency",
    "DependencyCreate",
    "DependencyGraph",
    "DependencyPath",
    "DependencyType",
    "GraphStats",
    "HealthStatus",
    "Service",
    "ServiceCreate",
    "TraceSpan",
    # Services
    "DependencyService",
    "get_dependency_service",
    "DependencyGraphAnalyzer",
    "DependencyDiscovery",
    "GraphVisualizer",
    # Router
    "router",
]
