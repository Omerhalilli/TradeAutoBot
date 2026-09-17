"""
Optimization & Backtesting Layer.
Provides high-speed vectorized backtesting, Walk-Forward Analysis (WFA),
Genetic Algorithm (GA) parameter optimization, and Particle Swarm Optimization (PSO).
"""

from autotrade.optimizer.backtester import Backtester, BacktestResult, BacktestTrade
from autotrade.optimizer.walk_forward import WalkForwardOptimizer, WalkForwardFold
from autotrade.optimizer.genetic_optimizer import GeneticOptimizer, Chromosome
from autotrade.optimizer.pso_optimizer import ParticleSwarmOptimizer, Particle
from autotrade.optimizer.parameter_calibrator import (
    ParameterCalibrator,
    CalibratedSymbolParams,
    parameter_calibrator,
)

__all__ = [
    "Backtester",
    "BacktestResult",
    "BacktestTrade",
    "WalkForwardOptimizer",
    "WalkForwardFold",
    "GeneticOptimizer",
    "Chromosome",
    "ParticleSwarmOptimizer",
    "Particle",
    "ParameterCalibrator",
    "CalibratedSymbolParams",
    "parameter_calibrator",
]
