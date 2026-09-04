"""
Walk-Forward Optimization & Anti-Overfitting Validation Engine.
Splits historical datasets into rolling In-Sample (IS) calibration windows
and Out-of-Sample (OOS) verification windows to evaluate Walk-Forward Efficiency (WFE).
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np

from autotrade.optimizer.backtester import Backtester, BacktestResult

logger = logging.getLogger("autotrade.optimizer.walk_forward")


@dataclass
class WalkForwardFold:
    """Represents a single rolling In-Sample and Out-of-Sample evaluation window."""
    fold_index: int
    in_sample_start: int
    in_sample_end: int
    out_of_sample_start: int
    out_of_sample_end: int
    best_params: Dict[str, Any] = field(default_factory=dict)
    is_sharpe: float = 0.0
    oos_sharpe: float = 0.0
    is_profit: float = 0.0
    oos_profit: float = 0.0
    walk_forward_efficiency: float = 0.0


class WalkForwardOptimizer:
    """
    Automated Walk-Forward Optimization Engine.
    Guarantees strategies maintain predictive alpha on unseen forward market data.
    """
    def __init__(
        self,
        backtester: Optional[Backtester] = None,
        n_folds: int = 4,
        is_ratio: float = 0.70
    ):
        self.backtester = backtester or Backtester()
        self.n_folds = n_folds
        self.is_ratio = is_ratio

    def create_folds(self, total_bars: int) -> List[WalkForwardFold]:
        """Calculates rolling chronological window boundaries."""
        folds: List[WalkForwardFold] = []
        step_size = total_bars // (self.n_folds + 1)
        window_size = int(step_size * 2)

        for i in range(self.n_folds):
            start = i * step_size
            end = min(start + window_size, total_bars)
            is_end = int(start + (end - start) * self.is_ratio)
            
            fold = WalkForwardFold(
                fold_index=i + 1,
                in_sample_start=start,
                in_sample_end=is_end,
                out_of_sample_start=is_end,
                out_of_sample_end=end
            )
            folds.append(fold)
        return folds

    def run_walk_forward(
        self,
        symbol: str,
        ohlcv: Dict[str, np.ndarray],
        strategy_factory_fn: Callable[[Dict[str, Any]], Callable],
        param_grid: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Runs Walk-Forward Analysis across all folds.
        Selects best parameters on In-Sample data, verifies on Out-of-Sample data.
        """
        total_bars = len(ohlcv["close"])
        folds = self.create_folds(total_bars)
        results: List[WalkForwardFold] = []

        for fold in folds:
            logger.info(f"Evaluating Walk-Forward Fold #{fold.fold_index} (IS: {fold.in_sample_start}-{fold.in_sample_end}, OOS: {fold.out_of_sample_start}-{fold.out_of_sample_end})")
            
            # Slice In-Sample data
            is_ohlcv = {k: v[fold.in_sample_start:fold.in_sample_end] for k, v in ohlcv.items()}
            
            # Grid search best params on In-Sample
            best_p = None
            best_is_sharpe = -999.0
            best_is_res = None

            for p in param_grid:
                eval_fn = strategy_factory_fn(p)
                res = self.backtester.run(symbol, is_ohlcv, eval_fn)
                if res.sharpe_ratio > best_is_sharpe and res.total_trades >= 3:
                    best_is_sharpe = res.sharpe_ratio
                    best_p = p
                    best_is_res = res

            fold.best_params = best_p or (param_grid[0] if param_grid else {})
            fold.is_sharpe = best_is_sharpe if best_is_res else 0.0
            fold.is_profit = best_is_res.net_profit if best_is_res else 0.0

            # Test chosen best parameters on Out-of-Sample data
            oos_ohlcv = {k: v[fold.out_of_sample_start:fold.out_of_sample_end] for k, v in ohlcv.items()}
            oos_eval_fn = strategy_factory_fn(fold.best_params)
            oos_res = self.backtester.run(symbol, oos_ohlcv, oos_eval_fn)

            fold.oos_sharpe = oos_res.sharpe_ratio
            fold.oos_profit = oos_res.net_profit

            # Calculate Walk-Forward Efficiency (WFE)
            if fold.is_profit > 0:
                fold.walk_forward_efficiency = max(0.0, (fold.oos_profit / fold.is_profit) * 100.0)
            else:
                fold.walk_forward_efficiency = 0.0

            results.append(fold)

        avg_wfe = float(np.mean([f.walk_forward_efficiency for f in results])) if results else 0.0
        is_robust = avg_wfe >= 50.0

        return {
            "symbol": symbol,
            "total_folds": len(results),
            "average_wfe_pct": round(avg_wfe, 2),
            "is_robust": is_robust,
            "folds": [
                {
                    "fold": f.fold_index,
                    "best_params": f.best_params,
                    "is_sharpe": round(f.is_sharpe, 2),
                    "oos_sharpe": round(f.oos_sharpe, 2),
                    "is_profit": round(f.is_profit, 2),
                    "oos_profit": round(f.oos_profit, 2),
                    "wfe_pct": round(f.walk_forward_efficiency, 1)
                }
                for f in results
            ]
        }
