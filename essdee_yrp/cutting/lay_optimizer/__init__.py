"""
Lay Planning Optimizer for Essdee MRP
======================================

Package for optimizing cutting lay plans across multiple strategies.

Usage (Python API):
    from . import optimize_lay_plan, optimize_all_strategies

    result = optimize_lay_plan(order, max_plies, max_pieces, strategy="direct_integer_search")
    results, failed = optimize_all_strategies(order, max_plies, max_pieces)

Author: VETRI (Essdee Production Intelligence)
Version: 4.1.0
Date: 2026-08-09
"""

from .core import (
	optimize_all_strategies,
	optimize_lay_plan,
)
from .display import print_comparison, print_plan

__version__ = "4.1.0"
__all__ = [
	"optimize_all_strategies",
	"optimize_lay_plan",
	"print_comparison",
	"print_plan",
]
