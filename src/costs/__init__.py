"""Incident Costs module for tracking and analyzing incident-related costs.

This module provides:
- Cost tracking across multiple categories (engineer time, revenue, cloud, SLA)
- Configurable hourly rates per engineer/team
- Revenue impact estimation based on service criticality
- SLA penalty calculations
- Cost trend analysis and reporting
- ROI calculation for prevention investments
- Team/department cost allocation
- Multi-currency support
"""

from .calculator import (
    CloudCostCalculator,
    CostCalculatorFactory,
    CustomerImpactCalculator,
    EngineerTimeCostCalculator,
    RevenueImpactCalculator,
    SLAPenaltyCalculator,
)
from .models import (
    CostCategory,
    CostEntry,
    CostReport,
    CostTrend,
    Currency,
    EngineerRate,
    IncidentCost,
    ROIAnalysis,
    ServiceCriticality,
    ServiceRevenueConfig,
    SLAConfig,
    TeamCostAllocation,
)
from .routes import get_cost_service, router, set_cost_service
from .service import CostService
from .store import CostStore, FileCostStore, InMemoryCostStore

__all__ = [
    # Models
    "CostCategory",
    "CostEntry",
    "CostReport",
    "CostTrend",
    "Currency",
    "EngineerRate",
    "IncidentCost",
    "ROIAnalysis",
    "ServiceCriticality",
    "ServiceRevenueConfig",
    "SLAConfig",
    "TeamCostAllocation",
    # Calculators
    "CloudCostCalculator",
    "CostCalculatorFactory",
    "CustomerImpactCalculator",
    "EngineerTimeCostCalculator",
    "RevenueImpactCalculator",
    "SLAPenaltyCalculator",
    # Store
    "CostStore",
    "FileCostStore",
    "InMemoryCostStore",
    # Service
    "CostService",
    # Routes
    "get_cost_service",
    "router",
    "set_cost_service",
]
