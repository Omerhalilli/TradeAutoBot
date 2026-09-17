"""
Walk-Forward Optimization & Anti-Overfitting Validation Engine.
Splits historical datasets into rolling In-Sample (IS) calibration windows
and Out-of-Sample (OOS) verification windows to evaluate Walk-Forward Efficiency (WFE).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from autotrade.optimizer.backtester import Backtester, BacktestResult
from autotrade.optimizer.genetic_optimizer import GeneticOptimizer

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
            
            # Grid search best params on In-Sample with concurrent execution
            best_p = None
            best_is_sharpe = -999.0
            best_is_res = None

            def _eval_param(p):
                eval_fn = strategy_factory_fn(p)
                res = self.backtester.run(symbol, is_ohlcv, eval_fn)
                return p, res

            if len(param_grid) > 4:
                with ThreadPoolExecutor() as executor:
                    futures = [executor.submit(_eval_param, p) for p in param_grid]
                    for fut in futures:
                        p, res = fut.result()
                        if res.sharpe_ratio > best_is_sharpe and res.total_trades >= 3:
                            best_is_sharpe = res.sharpe_ratio
                            best_p = p
                            best_is_res = res
            else:
                for p in param_grid:
                    p, res = _eval_param(p)
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

    def run_walk_forward_ga(
        self,
        symbol: str,
        ohlcv: Dict[str, np.ndarray],
        strategy_factory_fn: Callable[[Dict[str, Any]], Callable],
        param_bounds: Dict[str, Tuple[Any, Any, str]],
        population_size: int = 16,
        generations: int = 5,
        mutation_rate: float = 0.15
    ) -> Dict[str, Any]:
        """
        Executes hybrid Walk-Forward Genetic Optimization.
        In each rolling chronological fold, a Genetic Algorithm evolves optimal strategy parameters
        on In-Sample calibration data. Out-of-Sample verification then tests the evolved chromosome
        to measure Walk-Forward Efficiency (WFE) and prevent overfitting.
        """
        total_bars = len(ohlcv["close"])
        folds = self.create_folds(total_bars)
        results: List[WalkForwardFold] = []

        for fold in folds:
            logger.info(
                f"Evaluating Walk-Forward GA Fold #{fold.fold_index} "
                f"(IS: {fold.in_sample_start}-{fold.in_sample_end}, OOS: {fold.out_of_sample_start}-{fold.out_of_sample_end})"
            )

            # Slice In-Sample calibration data
            is_ohlcv = {k: v[fold.in_sample_start:fold.in_sample_end] for k, v in ohlcv.items()}

            # 1. Evolve optimal parameter configuration using Genetic Algorithm on In-Sample window
            ga = GeneticOptimizer(
                param_bounds=param_bounds,
                population_size=population_size,
                generations=generations,
                mutation_rate=mutation_rate
            )

            def _ga_fitness_fn(genes: Dict[str, Any]) -> Dict[str, float]:
                eval_fn = strategy_factory_fn(genes)
                bt_res = self.backtester.run(symbol, is_ohlcv, eval_fn)
                return {
                    "sharpe": bt_res.sharpe_ratio,
                    "profit_factor": bt_res.profit_factor,
                    "drawdown": bt_res.max_drawdown_pct
                }

            ga_res = ga.optimize(_ga_fitness_fn)
            best_p = ga_res.get("best_parameters", {})

            # Re-evaluate chosen best params on In-Sample to capture exact metrics
            is_eval_fn = strategy_factory_fn(best_p)
            is_res = self.backtester.run(symbol, is_ohlcv, is_eval_fn)

            fold.best_params = best_p
            fold.is_sharpe = is_res.sharpe_ratio
            fold.is_profit = is_res.net_profit

            # 2. Test chosen evolved parameters on unseen Out-of-Sample verification window
            oos_ohlcv = {k: v[fold.out_of_sample_start:fold.out_of_sample_end] for k, v in ohlcv.items()}
            oos_eval_fn = strategy_factory_fn(fold.best_params)
            oos_res = self.backtester.run(symbol, oos_ohlcv, oos_eval_fn)

            fold.oos_sharpe = oos_res.sharpe_ratio
            fold.oos_profit = oos_res.net_profit

            # 3. Calculate Walk-Forward Efficiency (WFE)
            if fold.is_profit > 0:
                fold.walk_forward_efficiency = max(0.0, (fold.oos_profit / fold.is_profit) * 100.0)
            else:
                fold.walk_forward_efficiency = 0.0

            results.append(fold)

        avg_wfe = float(np.mean([f.walk_forward_efficiency for f in results])) if results else 0.0
        is_robust = avg_wfe >= 50.0

        # Select overall winning parameter set: fold with highest OOS Sharpe having positive WFE
        sorted_folds = sorted(
            results,
            key=lambda f: (f.walk_forward_efficiency >= 40.0, f.oos_sharpe, f.oos_profit),
            reverse=True
        )
        winning_fold = sorted_folds[0] if sorted_folds else None
        overall_best_params = winning_fold.best_params if winning_fold else {}

        return {
            "symbol": symbol,
            "total_folds": len(results),
            "average_wfe_pct": round(avg_wfe, 2),
            "is_robust": is_robust,
            "winning_fold": winning_fold.fold_index if winning_fold else 0,
            "best_parameters": overall_best_params,
            "oos_sharpe": winning_fold.oos_sharpe if winning_fold else 0.0,
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
