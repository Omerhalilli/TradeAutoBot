"""
Analytics, Indicators, Charts & Mathematical Models Package.
Contains >50 technical indicators, visual multi-format chart generation,
and institutional quantitative/ML predictive models.
"""

from autotrade.analytics.precision import PrecisionMath, round_to_pip, round_to_lot
from autotrade.analytics.indicators import TechnicalIndicators, indicators
from autotrade.analytics.charts import ChartGenerator, ChartType
from autotrade.analytics.math_models import (
    PredictiveModels,
    MonteCarloResult,
    ARIMAForecast,
    GARCHVolatility,
    FFTCycle
)
from autotrade.analytics.adaptive_learner import (
    adaptive_learner,
    AdaptiveLearner,
    TradeMemory,
    TradeLearningRecord,
    ClusterPerformance,
    SymbolQuarantineStatus,
    MAEAdaptationStatus
)
from autotrade.analytics.historical_profiler import (
    historical_profiler,
    HistoricalProfiler,
    AssetDNA
)

__all__ = [
    "PrecisionMath",
    "round_to_pip",
    "round_to_lot",
    "TechnicalIndicators",
    "indicators",
    "run_fast_historical_replay",
    "ChartGenerator",
    "ChartType",
    "PredictiveModels",
    "MonteCarloResult",
    "ARIMAForecast",
    "GARCHVolatility",
    "FFTCycle",
    "adaptive_learner",
    "AdaptiveLearner",
    "TradeMemory",
    "TradeLearningRecord",
    "ClusterPerformance",
    "SymbolQuarantineStatus",
    "MAEAdaptationStatus",
    "historical_profiler",
    "HistoricalProfiler",
    "AssetDNA",
]
