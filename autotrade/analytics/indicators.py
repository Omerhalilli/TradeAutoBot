"""
Institutional Technical Analysis Engine with Over 50 Vectorized Mathematical Indicators.
Accelerated via Numba @njit(fastmath=True, nogil=True) for sub-millisecond calculation across thousands of bars.
Includes Market Regime Indicators: Kaufman Efficiency Ratio (KER) and Hurst Exponent (H).
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from numba import njit

logger = None


# ==============================================================================
# NUMBA JIT-COMPILED CORE KERNELS
# ==============================================================================

@njit(fastmath=True, nogil=True)
def _ema_kernel(data: np.ndarray, period: int) -> np.ndarray:
    n = len(data)
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out
    out[:] = np.nan
    if n < period or period < 1:
        return out
    alpha = 2.0 / (period + 1.0)
    out[0] = data[0]
    for i in range(1, n):
        out[i] = alpha * data[i] + (1.0 - alpha) * out[i - 1]
    out[:period - 1] = np.nan
    return out


@njit(fastmath=True, nogil=True)
def _wma_kernel(data: np.ndarray, period: int) -> np.ndarray:
    n = len(data)
    out = np.empty(n, dtype=np.float64)
    out[:] = np.nan
    if n < period or period < 1:
        return out
    w_sum = (period * (period + 1.0)) / 2.0
    for i in range(period - 1, n):
        dot = 0.0
        for j in range(period):
            dot += data[i - period + 1 + j] * (j + 1.0)
        out[i] = dot / w_sum
    return out


@njit(fastmath=True, nogil=True)
def _mcginley_kernel(data: np.ndarray, period: int) -> np.ndarray:
    n = len(data)
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out
    out[0] = data[0]
    k = 0.6 * period
    for i in range(1, n):
        c = data[i]
        prev = out[i - 1]
        denom = prev if prev > 1e-9 else 1e-9
        ratio = c / denom
        ratio4 = ratio * ratio * ratio * ratio
        out[i] = prev + (c - prev) / (k * ratio4)
    return out


@njit(fastmath=True, nogil=True)
def _rsi_kernel(data: np.ndarray, period: int) -> np.ndarray:
    n = len(data)
    rsi_vals = np.empty(n, dtype=np.float64)
    rsi_vals[:] = np.nan
    if n <= period or period < 1:
        return rsi_vals

    gains = np.empty(n - 1, dtype=np.float64)
    losses = np.empty(n - 1, dtype=np.float64)
    for i in range(n - 1):
        diff = data[i + 1] - data[i]
        if diff > 0.0:
            gains[i] = diff
            losses[i] = 0.0
        else:
            gains[i] = 0.0
            losses[i] = -diff

    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(period):
        avg_gain += gains[i]
        avg_loss += losses[i]
    avg_gain /= period
    avg_loss /= period

    if avg_loss == 0.0:
        rsi_vals[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_vals[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1.0) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1.0) + losses[i]) / period
        if avg_loss == 0.0:
            rsi_vals[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_vals[i + 1] = 100.0 - (100.0 / (1.0 + rs))
    return rsi_vals


@njit(fastmath=True, nogil=True)
def _atr_kernel(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    atr_vals = np.empty(n, dtype=np.float64)
    atr_vals[:] = np.nan
    if n < period or period < 1:
        return atr_vals

    tr = np.empty(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        h_l = high[i] - low[i]
        h_pc = abs(high[i] - close[i - 1])
        l_pc = abs(low[i] - close[i - 1])
        tr[i] = max(h_l, max(h_pc, l_pc))

    s = 0.0
    for i in range(period):
        s += tr[i]
    atr_vals[period - 1] = s / period

    for i in range(period, n):
        atr_vals[i] = (atr_vals[i - 1] * (period - 1.0) + tr[i]) / period
    return atr_vals


@njit(fastmath=True, nogil=True)
def _supertrend_kernel(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr_vals: np.ndarray,
    period: int,
    multiplier: float
):
    n = len(close)
    st = np.empty(n, dtype=np.float64)
    st[:] = np.nan
    direction = np.ones(n, dtype=np.int32)
    if n < period:
        return st, direction

    hl2 = (high + low) / 2.0
    upper_band = hl2 + multiplier * atr_vals
    lower_band = hl2 - multiplier * atr_vals

    for i in range(period, n):
        if close[i] > upper_band[i - 1]:
            direction[i] = 1
        elif close[i] < lower_band[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
            if direction[i] == 1 and lower_band[i] < lower_band[i - 1]:
                lower_band[i] = lower_band[i - 1]
            if direction[i] == -1 and upper_band[i] > upper_band[i - 1]:
                upper_band[i] = upper_band[i - 1]

        st[i] = lower_band[i] if direction[i] == 1 else upper_band[i]
    return st, direction


@njit(fastmath=True, nogil=True)
def _stochastic_kernel(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    k_period: int,
    d_period: int,
    slowing: int
):
    n = len(close)
    fast_k = np.empty(n, dtype=np.float64)
    fast_k[:] = np.nan
    slow_k = np.empty(n, dtype=np.float64)
    slow_k[:] = np.nan
    slow_d = np.empty(n, dtype=np.float64)
    slow_d[:] = np.nan

    if n < k_period:
        return fast_k, slow_k, slow_d

    for i in range(k_period - 1, n):
        h_max = high[i - k_period + 1]
        l_min = low[i - k_period + 1]
        for j in range(i - k_period + 2, i + 1):
            if high[j] > h_max:
                h_max = high[j]
            if low[j] < l_min:
                l_min = low[j]
        denom = h_max - l_min
        fast_k[i] = 100.0 * (close[i] - l_min) / denom if denom > 0.0 else 50.0

    # Slow %K
    for i in range(k_period - 1 + slowing - 1, n):
        s = 0.0
        for j in range(i - slowing + 1, i + 1):
            s += fast_k[j]
        slow_k[i] = s / slowing

    # Slow %D
    for i in range(k_period - 1 + slowing - 1 + d_period - 1, n):
        s = 0.0
        for j in range(i - d_period + 1, i + 1):
            s += slow_k[j]
        slow_d[i] = s / d_period

    return fast_k, slow_k, slow_d


@njit(fastmath=True, nogil=True)
def _bollinger_kernel(data: np.ndarray, period: int, num_std: float):
    n = len(data)
    mid = np.empty(n, dtype=np.float64)
    mid[:] = np.nan
    upper = np.empty(n, dtype=np.float64)
    upper[:] = np.nan
    lower = np.empty(n, dtype=np.float64)
    lower[:] = np.nan
    bandwidth = np.empty(n, dtype=np.float64)
    bandwidth[:] = np.nan
    percent_b = np.empty(n, dtype=np.float64)
    percent_b[:] = np.nan

    if n < period or period < 1:
        return mid, upper, lower, bandwidth, percent_b

    for i in range(period - 1, n):
        s = 0.0
        for j in range(i - period + 1, i + 1):
            s += data[j]
        m = s / period
        mid[i] = m

        var = 0.0
        for j in range(i - period + 1, i + 1):
            diff = data[j] - m
            var += diff * diff
        std = math.sqrt(var / period)
        upper[i] = m + num_std * std
        lower[i] = m - num_std * std
        bw = upper[i] - lower[i]
        bandwidth[i] = (bw / m) * 100.0 if m > 0.0 else 0.0
        percent_b[i] = (data[i] - lower[i]) / bw if bw > 0.0 else 0.5

    return mid, upper, lower, bandwidth, percent_b


@njit(fastmath=True, nogil=True)
def _adx_kernel(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int):
    n = len(close)
    adx_vals = np.empty(n, dtype=np.float64)
    adx_vals[:] = np.nan
    plus_di = np.empty(n, dtype=np.float64)
    plus_di[:] = np.nan
    minus_di = np.empty(n, dtype=np.float64)
    minus_di[:] = np.nan

    if n <= 2 * period:
        return adx_vals, plus_di, minus_di

    atr_vals = _atr_kernel(high, low, close, period)

    plus_dm = np.zeros(n, dtype=np.float64)
    minus_dm = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        if up_move > down_move and up_move > 0.0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0.0:
            minus_dm[i] = down_move

    p_dm_smooth = _ema_kernel(plus_dm, period)
    m_dm_smooth = _ema_kernel(minus_dm, period)

    dx = np.empty(n, dtype=np.float64)
    dx[:] = np.nan

    for i in range(period, n):
        denom = atr_vals[i]
        if denom > 0.0:
            plus_di[i] = 100.0 * (p_dm_smooth[i] / denom)
            minus_di[i] = 100.0 * (m_dm_smooth[i] / denom)
            di_sum = plus_di[i] + minus_di[i]
            if di_sum > 0.0:
                dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum

    adx_smooth = _ema_kernel(dx[period:], period)
    for i in range(len(adx_smooth)):
        adx_vals[period + i] = adx_smooth[i]

    return adx_vals, plus_di, minus_di


@njit(fastmath=True, nogil=True)
def _zigzag_kernel(high: np.ndarray, low: np.ndarray, deviation_pct: float = 0.5):
    n = len(high)
    if n < 3:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64), np.empty(0, dtype=np.int32)

    piv_idx = np.empty(n, dtype=np.int64)
    piv_price = np.empty(n, dtype=np.float64)
    piv_type = np.empty(n, dtype=np.int32)
    count = 0

    is_searching_high = high[1] > high[0]
    cur_pivot_idx = 0
    cur_pivot_price = low[0] if is_searching_high else high[0]

    for i in range(1, n):
        if is_searching_high:
            if high[i] > cur_pivot_price:
                cur_pivot_price = high[i]
                cur_pivot_idx = i
            elif (cur_pivot_price - low[i]) / cur_pivot_price * 100.0 >= deviation_pct:
                piv_idx[count] = cur_pivot_idx
                piv_price[count] = cur_pivot_price
                piv_type[count] = 1  # HIGH
                count += 1
                is_searching_high = False
                cur_pivot_price = low[i]
                cur_pivot_idx = i
        else:
            if low[i] < cur_pivot_price:
                cur_pivot_price = low[i]
                cur_pivot_idx = i
            elif (high[i] - cur_pivot_price) / cur_pivot_price * 100.0 >= deviation_pct:
                piv_idx[count] = cur_pivot_idx
                piv_price[count] = cur_pivot_price
                piv_type[count] = -1  # LOW
                count += 1
                is_searching_high = True
                cur_pivot_price = high[i]
                cur_pivot_idx = i

    piv_idx[count] = cur_pivot_idx
    piv_price[count] = cur_pivot_price
    piv_type[count] = 1 if is_searching_high else -1
    count += 1

    return piv_idx[:count], piv_price[:count], piv_type[:count]


@njit(fastmath=True, nogil=True)
def _kaufman_efficiency_ratio_kernel(close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    er = np.empty(n, dtype=np.float64)
    er[:] = np.nan
    if n <= period or period < 1:
        return er

    for i in range(period, n):
        direction = abs(close[i] - close[i - period])
        vol = 0.0
        for j in range(i - period, i):
            vol += abs(close[j + 1] - close[j])
        er[i] = direction / vol if vol > 0.0 else 0.0
    return er


@njit(fastmath=True, nogil=True)
def _hurst_exponent_kernel(close: np.ndarray, max_lags: int = 20) -> float:
    """
    Computes Hurst Exponent via rescaled range (R/S) analysis.
    H > 0.55: Persistent / Trending
    H < 0.45: Mean-Reverting
    0.45 <= H <= 0.55: Random Walk / Choppy Noise
    """
    n = len(close)
    if n < 30:
        return 0.50

    max_lag = min(max_lags, n // 2)
    if max_lag < 4:
        return 0.50

    lags = np.arange(4, max_lag + 1)
    n_lags = len(lags)
    log_lags = np.empty(n_lags, dtype=np.float64)
    log_rs = np.empty(n_lags, dtype=np.float64)

    returns = np.empty(n - 1, dtype=np.float64)
    for i in range(n - 1):
        returns[i] = close[i + 1] - close[i]

    for idx in range(n_lags):
        lag = lags[idx]
        num_sub = len(returns) // lag
        if num_sub < 1:
            log_lags[idx] = math.log(float(lag))
            log_rs[idx] = 0.0
            continue
        rs_sum = 0.0
        valid_sub = 0
        for s in range(num_sub):
            start = s * lag
            end = start + lag
            m_sub = 0.0
            for j in range(start, end):
                m_sub += returns[j]
            m_sub /= lag

            cum_dev = 0.0
            min_cum = 0.0
            max_cum = 0.0
            var_sub = 0.0
            for j in range(start, end):
                dev = returns[j] - m_sub
                cum_dev += dev
                if cum_dev < min_cum:
                    min_cum = cum_dev
                if cum_dev > max_cum:
                    max_cum = cum_dev
                var_sub += dev * dev
            s_std = math.sqrt(var_sub / lag)
            r_range = max_cum - min_cum
            if s_std > 1e-9:
                rs_sum += r_range / s_std
                valid_sub += 1

        log_lags[idx] = math.log(float(lag))
        if valid_sub > 0:
            log_rs[idx] = math.log(rs_sum / valid_sub)
        else:
            log_rs[idx] = 0.0

    x_mean = 0.0
    y_mean = 0.0
    for i in range(n_lags):
        x_mean += log_lags[i]
        y_mean += log_rs[i]
    x_mean /= n_lags
    y_mean /= n_lags

    num = 0.0
    den = 0.0
    for i in range(n_lags):
        dx = log_lags[i] - x_mean
        num += dx * (log_rs[i] - y_mean)
        den += dx * dx

    if den > 1e-12:
        H = num / den
    else:
        H = 0.50
    return max(0.0, min(1.0, float(H)))


@njit(fastmath=True, nogil=True)
def _cmf_kernel(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    period: int
) -> np.ndarray:
    n = len(close)
    cmf_vals = np.empty(n, dtype=np.float64)
    cmf_vals[:] = np.nan
    if n < period or period < 1:
        return cmf_vals

    mfv = np.empty(n, dtype=np.float64)
    for i in range(n):
        hl = high[i] - low[i]
        if hl > 0.0:
            mfv[i] = (((close[i] - low[i]) - (high[i] - close[i])) / hl) * volume[i]
        else:
            mfv[i] = 0.0

    for i in range(period - 1, n):
        sum_vol = 0.0
        sum_mfv = 0.0
        for j in range(i - period + 1, i + 1):
            sum_vol += volume[j]
            sum_mfv += mfv[j]
        cmf_vals[i] = sum_mfv / sum_vol if sum_vol > 0.0 else 0.0
    return cmf_vals


# ==============================================================================
# MASTER TECHNICAL INDICATORS SUITE (NUMBA ACCELERATED)
# ==============================================================================

class TechnicalIndicators:
    """
    Comprehensive quantitative technical indicator calculation suite.
    All methods accept 1D numpy arrays or Python lists of floats and return vectorized results.
    Accelerated with Numba JIT kernels for sub-millisecond execution.
    """

    # --------------------------------------------------------------------------
    # 1. Moving Averages Suite
    # --------------------------------------------------------------------------
    @staticmethod
    def sma(data: np.ndarray, period: int = 14) -> np.ndarray:
        """1. Simple Moving Average (SMA)."""
        data = np.asarray(data, dtype=np.float64)
        if len(data) < period:
            return np.full_like(data, np.nan)
        weights = np.ones(period) / period
        res = np.convolve(data, weights, mode="full")[:len(data)]
        res[:period - 1] = np.nan
        return res

    @staticmethod
    def ema(data: np.ndarray, period: int = 14) -> np.ndarray:
        """2. Exponential Moving Average (EMA). Numba JIT accelerated."""
        arr = np.ascontiguousarray(data, dtype=np.float64)
        return _ema_kernel(arr, int(period))

    @staticmethod
    def wma(data: np.ndarray, period: int = 14) -> np.ndarray:
        """3. Weighted Moving Average (WMA). Numba JIT accelerated."""
        arr = np.ascontiguousarray(data, dtype=np.float64)
        return _wma_kernel(arr, int(period))

    @classmethod
    def hma(cls, data: np.ndarray, period: int = 14) -> np.ndarray:
        """4. Hull Moving Average (HMA). Reduces lag using weighted combinations."""
        half_p = max(1, period // 2)
        sqrt_p = max(1, int(math.sqrt(period)))
        wma_half = cls.wma(data, half_p)
        wma_full = cls.wma(data, period)
        diff = 2.0 * wma_half - wma_full
        return cls.wma(diff, sqrt_p)

    @classmethod
    def dema(cls, data: np.ndarray, period: int = 14) -> np.ndarray:
        """5. Double Exponential Moving Average (DEMA)."""
        ema1 = cls.ema(data, period)
        ema2 = cls.ema(ema1, period)
        return 2.0 * ema1 - ema2

    @classmethod
    def tema(cls, data: np.ndarray, period: int = 14) -> np.ndarray:
        """6. Triple Exponential Moving Average (TEMA)."""
        ema1 = cls.ema(data, period)
        ema2 = cls.ema(ema1, period)
        ema3 = cls.ema(ema2, period)
        return 3.0 * ema1 - 3.0 * ema2 + ema3

    @staticmethod
    def mcginley_dynamic(data: np.ndarray, period: int = 14) -> np.ndarray:
        """7. McGinley Dynamic. Numba JIT accelerated."""
        arr = np.ascontiguousarray(data, dtype=np.float64)
        return _mcginley_kernel(arr, int(period))

    # --------------------------------------------------------------------------
    # 2. Oscillators & Momentum
    # --------------------------------------------------------------------------
    @staticmethod
    def rsi(data: np.ndarray, period: int = 14) -> np.ndarray:
        """8. Relative Strength Index (RSI). Numba JIT accelerated."""
        arr = np.ascontiguousarray(data, dtype=np.float64)
        return _rsi_kernel(arr, int(period))

    @classmethod
    def macd(
        cls,
        data: np.ndarray,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Dict[str, np.ndarray]:
        """9. Moving Average Convergence Divergence (MACD)."""
        fast_ema = cls.ema(data, fast_period)
        slow_ema = cls.ema(data, slow_period)
        macd_line = fast_ema - slow_ema
        signal_line = cls.ema(macd_line, signal_period)
        hist = macd_line - signal_line
        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": hist
        }

    @staticmethod
    def stochastic(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        k_period: int = 14,
        d_period: int = 3,
        slowing: int = 3
    ) -> Dict[str, np.ndarray]:
        """10. Stochastic Oscillator (%K, %D, Slow %D). Numba JIT accelerated."""
        h = np.ascontiguousarray(high, dtype=np.float64)
        l = np.ascontiguousarray(low, dtype=np.float64)
        c = np.ascontiguousarray(close, dtype=np.float64)
        fk, sk, sd = _stochastic_kernel(h, l, c, int(k_period), int(d_period), int(slowing))
        return {"fast_k": fk, "slow_k": sk, "slow_d": sd}

    @staticmethod
    def williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """11. Williams %R."""
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        n = len(close)
        r = np.full(n, np.nan)
        for i in range(period - 1, n):
            h = np.max(high[i - period + 1:i + 1])
            l = np.min(low[i - period + 1:i + 1])
            denom = h - l
            r[i] = -100.0 * (h - close[i]) / denom if denom > 0 else -50.0
        return r

    @staticmethod
    def cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 20) -> np.ndarray:
        """12. Commodity Channel Index (CCI)."""
        tp = (np.asarray(high, dtype=np.float64) + np.asarray(low, dtype=np.float64) + np.asarray(close, dtype=np.float64)) / 3.0
        n = len(tp)
        cci_vals = np.full(n, np.nan)
        for i in range(period - 1, n):
            window = tp[i - period + 1:i + 1]
            mean = np.mean(window)
            md = np.mean(np.abs(window - mean))
            cci_vals[i] = (tp[i] - mean) / (0.015 * md) if md > 0 else 0.0
        return cci_vals

    @staticmethod
    def momentum(close: np.ndarray, period: int = 14) -> np.ndarray:
        """13. Momentum Indicator (MOM)."""
        close = np.asarray(close, dtype=np.float64)
        mom = np.full_like(close, np.nan)
        if len(close) > period:
            mom[period:] = close[period:] - close[:-period]
        return mom

    @staticmethod
    def roc(close: np.ndarray, period: int = 12) -> np.ndarray:
        """14. Rate of Change (ROC)."""
        close = np.asarray(close, dtype=np.float64)
        res = np.full_like(close, np.nan)
        if len(close) > period:
            denom = close[:-period]
            res[period:] = np.where(denom != 0, 100.0 * (close[period:] - denom) / denom, 0.0)
        return res

    @staticmethod
    def cmo(close: np.ndarray, period: int = 14) -> np.ndarray:
        """15. Chande Momentum Oscillator (CMO)."""
        close = np.asarray(close, dtype=np.float64)
        n = len(close)
        if n <= period:
            return np.full_like(close, np.nan)
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        cmo_vals = np.full_like(close, np.nan)
        for i in range(period, n):
            s_g = np.sum(gains[i - period:i])
            s_l = np.sum(losses[i - period:i])
            denom = s_g + s_l
            cmo_vals[i] = 100.0 * (s_g - s_l) / denom if denom > 0 else 0.0
        return cmo_vals

    @classmethod
    def tsi(cls, close: np.ndarray, long_period: int = 25, short_period: int = 13) -> np.ndarray:
        """16. True Strength Index (TSI)."""
        close = np.asarray(close, dtype=np.float64)
        if len(close) < 2:
            return np.full_like(close, np.nan)
        diff = np.zeros_like(close)
        diff[1:] = np.diff(close)
        abs_diff = np.abs(diff)

        smooth1 = cls.ema(diff, long_period)
        smooth2 = cls.ema(smooth1, short_period)

        abs_smooth1 = cls.ema(abs_diff, long_period)
        abs_smooth2 = cls.ema(abs_smooth1, short_period)

        return np.where(abs_smooth2 != 0, 100.0 * (smooth2 / abs_smooth2), 0.0)

    @staticmethod
    def awesome_oscillator(high: np.ndarray, low: np.ndarray) -> np.ndarray:
        """17. Awesome Oscillator (AO)."""
        mp = (np.asarray(high, dtype=np.float64) + np.asarray(low, dtype=np.float64)) / 2.0
        sma5 = TechnicalIndicators.sma(mp, 5)
        sma34 = TechnicalIndicators.sma(mp, 34)
        return sma5 - sma34

    @classmethod
    def accelerator_oscillator(cls, high: np.ndarray, low: np.ndarray) -> np.ndarray:
        """18. Accelerator Oscillator (AC)."""
        ao = cls.awesome_oscillator(high, low)
        ao_sma5 = cls.sma(ao, 5)
        return ao - ao_sma5

    # --------------------------------------------------------------------------
    # 3. Volatility & Bands Suite
    # --------------------------------------------------------------------------
    @staticmethod
    def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """19. Average True Range (ATR). Numba JIT accelerated."""
        h = np.ascontiguousarray(high, dtype=np.float64)
        l = np.ascontiguousarray(low, dtype=np.float64)
        c = np.ascontiguousarray(close, dtype=np.float64)
        return _atr_kernel(h, l, c, int(period))

    @classmethod
    def natr(cls, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """20. Normalized Average True Range (NATR)."""
        atr_vals = cls.atr(high, low, close, period)
        close_arr = np.asarray(close, dtype=np.float64)
        return np.where(close_arr > 0, 100.0 * (atr_vals / close_arr), 0.0)

    @classmethod
    def bollinger_bands(
        cls,
        data: np.ndarray,
        period: int = 20,
        num_std: float = 2.0
    ) -> Dict[str, np.ndarray]:
        """21. Bollinger Bands. Numba JIT accelerated."""
        arr = np.ascontiguousarray(data, dtype=np.float64)
        mid, up, low, bw, pb = _bollinger_kernel(arr, int(period), float(num_std))
        return {
            "middle": mid,
            "upper": up,
            "lower": low,
            "bandwidth": bw,
            "percent_b": pb
        }

    @classmethod
    def keltner_channels(
        cls,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 20,
        atr_period: int = 10,
        multiplier: float = 2.0
    ) -> Dict[str, np.ndarray]:
        """22. Keltner Channels."""
        mid = cls.ema(close, period)
        atr_val = cls.atr(high, low, close, atr_period)
        upper = mid + multiplier * atr_val
        lower = mid - multiplier * atr_val
        return {"middle": mid, "upper": upper, "lower": lower}

    @staticmethod
    def donchian_channels(high: np.ndarray, low: np.ndarray, period: int = 20) -> Dict[str, np.ndarray]:
        """23. Donchian Channels."""
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        n = len(high)
        upper = np.full(n, np.nan)
        lower = np.full(n, np.nan)
        mid = np.full(n, np.nan)
        for i in range(period - 1, n):
            upper[i] = np.max(high[i - period + 1:i + 1])
            lower[i] = np.min(low[i - period + 1:i + 1])
            mid[i] = (upper[i] + lower[i]) / 2.0
        return {"upper": upper, "lower": lower, "middle": mid}

    @classmethod
    def supertrend(
        cls,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 10,
        multiplier: float = 3.0
    ) -> Dict[str, np.ndarray]:
        """24. SuperTrend Indicator. Numba JIT accelerated."""
        h = np.ascontiguousarray(high, dtype=np.float64)
        l = np.ascontiguousarray(low, dtype=np.float64)
        c = np.ascontiguousarray(close, dtype=np.float64)
        atr_vals = _atr_kernel(h, l, c, int(period))
        st, direction = _supertrend_kernel(h, l, c, atr_vals, int(period), float(multiplier))
        return {"supertrend": st, "direction": direction}

    @staticmethod
    def historical_volatility(close: np.ndarray, period: int = 20, annual_factor: float = 252.0) -> np.ndarray:
        """25. Historical Volatility."""
        close = np.asarray(close, dtype=np.float64)
        n = len(close)
        hv = np.full(n, np.nan)
        if n < period + 1:
            return hv
        log_ret = np.log(close[1:] / close[:-1])
        sqrt_ann = math.sqrt(annual_factor)
        for i in range(period - 1, len(log_ret)):
            std = np.std(log_ret[i - period + 1:i + 1])
            hv[i + 1] = std * sqrt_ann * 100.0
        return hv

    # --------------------------------------------------------------------------
    # 4. Trend & Directional Suite
    # --------------------------------------------------------------------------
    @classmethod
    def adx(
        cls,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14
    ) -> Dict[str, np.ndarray]:
        """26. Average Directional Index (ADX, +DI, -DI). Numba JIT accelerated."""
        h = np.ascontiguousarray(high, dtype=np.float64)
        l = np.ascontiguousarray(low, dtype=np.float64)
        c = np.ascontiguousarray(close, dtype=np.float64)
        adx_vals, plus_di, minus_di = _adx_kernel(h, l, c, int(period))
        return {"adx": adx_vals, "plus_di": plus_di, "minus_di": minus_di}

    @staticmethod
    def ichimoku(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_b_period: int = 52
    ) -> Dict[str, np.ndarray]:
        """27. Ichimoku Kinko Hyo."""
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        n = len(close)

        def hl_mean(p: int) -> np.ndarray:
            res = np.full(n, np.nan)
            for i in range(p - 1, n):
                res[i] = (np.max(high[i - p + 1:i + 1]) + np.min(low[i - p + 1:i + 1])) / 2.0
            return res

        tenkan = hl_mean(tenkan_period)
        kijun = hl_mean(kijun_period)
        senkou_a = (tenkan + kijun) / 2.0
        senkou_b = hl_mean(senkou_b_period)
        chikou = np.full(n, np.nan)
        chikou[:-kijun_period] = close[kijun_period:]

        return {
            "tenkan_sen": tenkan,
            "kijun_sen": kijun,
            "senkou_span_a": senkou_a,
            "senkou_span_b": senkou_b,
            "chikou_span": chikou
        }

    @staticmethod
    def parabolic_sar(
        high: np.ndarray,
        low: np.ndarray,
        step: float = 0.02,
        max_step: float = 0.20
    ) -> np.ndarray:
        """28. Parabolic Stop and Reverse (SAR)."""
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        n = len(high)
        sar = np.full(n, np.nan)
        if n < 2:
            return sar

        is_bull = high[1] > high[0]
        af = step
        ep = high[1] if is_bull else low[1]
        sar[1] = low[0] if is_bull else high[0]

        for i in range(2, n):
            prev_sar = sar[i - 1]
            if is_bull:
                cur_sar = prev_sar + af * (ep - prev_sar)
                cur_sar = min(cur_sar, low[i - 1], low[i - 2])
                if low[i] < cur_sar:
                    is_bull = False
                    cur_sar = ep
                    ep = low[i]
                    af = step
                else:
                    if high[i] > ep:
                        ep = high[i]
                        af = min(af + step, max_step)
            else:
                cur_sar = prev_sar - af * (prev_sar - ep)
                cur_sar = max(cur_sar, high[i - 1], high[i - 2])
                if high[i] > cur_sar:
                    is_bull = True
                    cur_sar = ep
                    ep = high[i]
                    af = step
                else:
                    if low[i] < ep:
                        ep = low[i]
                        af = min(af + step, max_step)
            sar[i] = cur_sar

        return sar

    @staticmethod
    def aroon(high: np.ndarray, low: np.ndarray, period: int = 25) -> Dict[str, np.ndarray]:
        """29. Aroon Indicator."""
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        n = len(high)
        aroon_up = np.full(n, np.nan)
        aroon_down = np.full(n, np.nan)
        for i in range(period, n):
            h_win = high[i - period:i + 1]
            l_win = low[i - period:i + 1]
            h_idx = np.argmax(h_win)
            l_idx = np.argmin(l_win)
            aroon_up[i] = (h_idx / float(period)) * 100.0
            aroon_down[i] = (l_idx / float(period)) * 100.0
        return {"aroon_up": aroon_up, "aroon_down": aroon_down, "oscillator": aroon_up - aroon_down}

    @staticmethod
    def vortex(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> Dict[str, np.ndarray]:
        """30. Vortex Indicator (+VI, -VI)."""
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        n = len(close)
        vm_plus = np.abs(high[1:] - low[:-1])
        vm_minus = np.abs(low[1:] - high[:-1])

        tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
        vi_plus = np.full(n, np.nan)
        vi_minus = np.full(n, np.nan)

        for i in range(period - 1, len(tr)):
            sum_tr = np.sum(tr[i - period + 1:i + 1])
            if sum_tr > 0:
                vi_plus[i + 1] = np.sum(vm_plus[i - period + 1:i + 1]) / sum_tr
                vi_minus[i + 1] = np.sum(vm_minus[i - period + 1:i + 1]) / sum_tr
        return {"plus_vi": vi_plus, "minus_vi": vi_minus}

    @classmethod
    def elder_ray(cls, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 13) -> Dict[str, np.ndarray]:
        """31. Elder Ray Index."""
        ema_val = cls.ema(close, period)
        bull = np.asarray(high, dtype=np.float64) - ema_val
        bear = np.asarray(low, dtype=np.float64) - ema_val
        return {"bull_power": bull, "bear_power": bear}

    # --------------------------------------------------------------------------
    # 5. Volume & Flow Indicators
    # --------------------------------------------------------------------------
    @staticmethod
    def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """32. On-Balance Volume (OBV)."""
        close = np.asarray(close, dtype=np.float64)
        vol = np.asarray(volume, dtype=np.float64)
        n = len(close)
        if n == 0:
            return np.empty(0, dtype=np.float64)
        obv_vals = np.empty_like(close)
        obv_vals[0] = vol[0]
        for i in range(1, n):
            if close[i] > close[i - 1]:
                obv_vals[i] = obv_vals[i - 1] + vol[i]
            elif close[i] < close[i - 1]:
                obv_vals[i] = obv_vals[i - 1] - vol[i]
            else:
                obv_vals[i] = obv_vals[i - 1]
        return obv_vals

    @staticmethod
    def vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """33. Volume Weighted Average Price (VWAP)."""
        tp = (np.asarray(high, dtype=np.float64) + np.asarray(low, dtype=np.float64) + np.asarray(close, dtype=np.float64)) / 3.0
        vol = np.asarray(volume, dtype=np.float64)
        cum_tp_vol = np.cumsum(tp * vol)
        cum_vol = np.cumsum(vol)
        return np.where(cum_vol > 0, cum_tp_vol / cum_vol, tp)

    @staticmethod
    def cmf(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, period: int = 20) -> np.ndarray:
        """34. Chaikin Money Flow (CMF). Numba JIT accelerated."""
        h = np.ascontiguousarray(high, dtype=np.float64)
        l = np.ascontiguousarray(low, dtype=np.float64)
        c = np.ascontiguousarray(close, dtype=np.float64)
        v = np.ascontiguousarray(volume, dtype=np.float64)
        return _cmf_kernel(h, l, c, v, int(period))

    @staticmethod
    def mfi(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, period: int = 14) -> np.ndarray:
        """35. Money Flow Index (MFI)."""
        tp = (np.asarray(high, dtype=np.float64) + np.asarray(low, dtype=np.float64) + np.asarray(close, dtype=np.float64)) / 3.0
        vol = np.asarray(volume, dtype=np.float64)
        raw_mf = tp * vol
        n = len(tp)
        mfi_vals = np.full(n, np.nan)
        for i in range(period, n):
            pos_mf = sum(raw_mf[j] for j in range(i - period + 1, i + 1) if tp[j] > tp[j - 1])
            neg_mf = sum(raw_mf[j] for j in range(i - period + 1, i + 1) if tp[j] < tp[j - 1])
            if neg_mf == 0:
                mfi_vals[i] = 100.0
            else:
                mfi_vals[i] = 100.0 - (100.0 / (1.0 + pos_mf / neg_mf))
        return mfi_vals

    @classmethod
    def force_index(cls, close: np.ndarray, volume: np.ndarray, period: int = 13) -> np.ndarray:
        """36. Force Index."""
        close = np.asarray(close, dtype=np.float64)
        vol = np.asarray(volume, dtype=np.float64)
        raw_fi = np.zeros_like(close)
        if len(close) > 1:
            raw_fi[1:] = np.diff(close) * vol[1:]
        return cls.ema(raw_fi, period)

    @staticmethod
    def eom(high: np.ndarray, low: np.ndarray, volume: np.ndarray, period: int = 14) -> np.ndarray:
        """37. Ease of Movement (EOM)."""
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        vol = np.asarray(volume, dtype=np.float64)
        dm = ((high[1:] + low[1:]) / 2.0) - ((high[:-1] + low[:-1]) / 2.0)
        hl = high[1:] - low[1:]
        br = np.where(hl > 0, (vol[1:] / 10000.0) / hl, 1.0)
        eom_raw = np.where(br > 0, dm / br, 0.0)
        n = len(high)
        res = np.full(n, np.nan)
        for i in range(period - 1, len(eom_raw)):
            res[i + 1] = np.mean(eom_raw[i - period + 1:i + 1])
        return res

    @staticmethod
    def pvt(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """38. Price Volume Trend (PVT)."""
        close = np.asarray(close, dtype=np.float64)
        vol = np.asarray(volume, dtype=np.float64)
        pvt_vals = np.zeros_like(close)
        for i in range(1, len(close)):
            pct = (close[i] - close[i - 1]) / close[i - 1] if close[i - 1] != 0 else 0.0
            pvt_vals[i] = pvt_vals[i - 1] + pct * vol[i]
        return pvt_vals

    # --------------------------------------------------------------------------
    # 6. Advanced Structural, Wave, Cycle & Swing Analysis
    # --------------------------------------------------------------------------
    @staticmethod
    def zigzag(high: np.ndarray, low: np.ndarray, deviation_pct: float = 0.5) -> List[Tuple[int, float, str]]:
        """39. ZigZag Swing High/Low Pivot Detector. Numba JIT accelerated."""
        h = np.ascontiguousarray(high, dtype=np.float64)
        l = np.ascontiguousarray(low, dtype=np.float64)
        idx_arr, price_arr, type_arr = _zigzag_kernel(h, l, float(deviation_pct))
        pivots: List[Tuple[int, float, str]] = []
        for i in range(len(idx_arr)):
            pivots.append((int(idx_arr[i]), float(price_arr[i]), "HIGH" if type_arr[i] == 1 else "LOW"))
        return pivots

    @classmethod
    def elliott_wave(cls, high: np.ndarray, low: np.ndarray) -> Dict[str, Any]:
        """40. Elliott Wave Analyzer."""
        pivots = cls.zigzag(high, low, deviation_pct=0.3)
        if len(pivots) < 6:
            return {"pattern": "INSUFFICIENT_DATA", "waves": []}

        p5 = pivots[-5:]
        wave_types = [p[2] for p in p5]
        is_bullish_impulse = (
            wave_types == ["LOW", "HIGH", "LOW", "HIGH", "LOW"] or
            wave_types == ["HIGH", "LOW", "HIGH", "LOW", "HIGH"]
        )

        return {
            "pattern": "BULLISH_IMPULSE_5" if is_bullish_impulse else "CORRECTIVE_OR_RANGE",
            "pivots_count": len(pivots),
            "recent_waves": [{"index": p[0], "price": p[1], "type": p[2]} for p in p5]
        }

    @staticmethod
    def fibonacci_levels(high_price: float, low_price: float) -> Dict[str, float]:
        """41. Fibonacci Retracements & Extensions."""
        diff = high_price - low_price
        return {
            "fib_0": high_price,
            "fib_236": high_price - 0.236 * diff,
            "fib_382": high_price - 0.382 * diff,
            "fib_500": high_price - 0.500 * diff,
            "fib_618": high_price - 0.618 * diff,
            "fib_786": high_price - 0.786 * diff,
            "fib_100": low_price,
            "ext_1272": high_price + 0.272 * diff,
            "ext_1618": high_price + 0.618 * diff
        }

    @staticmethod
    def pivot_points(high: float, low: float, close: float) -> Dict[str, float]:
        """42. Standard & Camarilla Pivot Points."""
        p = (high + low + close) / 3.0
        r1 = 2.0 * p - low
        s1 = 2.0 * p - high
        r2 = p + (high - low)
        s2 = p - (high - low)
        r3 = high + 2.0 * (p - low)
        s3 = low - 2.0 * (high - p)

        diff = high - low
        h4 = close + diff * 1.1 / 2.0
        h3 = close + diff * 1.1 / 4.0
        l3 = close - diff * 1.1 / 4.0
        l4 = close - diff * 1.1 / 2.0

        return {
            "pivot": round(p, 5),
            "r1": round(r1, 5), "s1": round(s1, 5),
            "r2": round(r2, 5), "s2": round(s2, 5),
            "r3": round(r3, 5), "s3": round(s3, 5),
            "camarilla_h4": round(h4, 5), "camarilla_h3": round(h3, 5),
            "camarilla_l3": round(l3, 5), "camarilla_l4": round(l4, 5)
        }

    @staticmethod
    def dpo(close: np.ndarray, period: int = 20) -> np.ndarray:
        """43. Detrended Price Oscillator (DPO)."""
        close = np.asarray(close, dtype=np.float64)
        shift = int(period / 2.0 + 1)
        sma_val = TechnicalIndicators.sma(close, period)
        res = np.full_like(close, np.nan)
        if len(close) > shift:
            res[shift:] = close[shift:] - sma_val[:-shift]
        return res

    @classmethod
    def coppock_curve(cls, close: np.ndarray, r1: int = 14, r2: int = 11, wma_p: int = 10) -> np.ndarray:
        """44. Coppock Curve."""
        roc1 = cls.roc(close, r1)
        roc2 = cls.roc(close, r2)
        return cls.wma(roc1 + roc2, wma_p)

    @classmethod
    def mass_index(cls, high: np.ndarray, low: np.ndarray, ema_p: int = 9, sum_p: int = 25) -> np.ndarray:
        """45. Mass Index."""
        hl = np.asarray(high, dtype=np.float64) - np.asarray(low, dtype=np.float64)
        ema1 = cls.ema(hl, ema_p)
        ema2 = cls.ema(ema1, ema_p)
        ratio = np.where(ema2 > 0, ema1 / ema2, 1.0)
        n = len(high)
        res = np.full(n, np.nan)
        for i in range(sum_p - 1, n):
            res[i] = np.sum(ratio[i - sum_p + 1:i + 1])
        return res

    @classmethod
    def kst(cls, close: np.ndarray) -> Dict[str, np.ndarray]:
        """46. Know Sure Thing (KST)."""
        rcma1 = cls.sma(cls.roc(close, 10), 10)
        rcma2 = cls.sma(cls.roc(close, 15), 10)
        rcma3 = cls.sma(cls.roc(close, 20), 10)
        rcma4 = cls.sma(cls.roc(close, 30), 15)
        kst_line = rcma1 * 1.0 + rcma2 * 2.0 + rcma3 * 3.0 + rcma4 * 4.0
        signal_line = cls.sma(kst_line, 9)
        return {"kst": kst_line, "signal": signal_line}

    @staticmethod
    def balance_of_power(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        """47. Balance of Power (BOP)."""
        hl = np.asarray(high, dtype=np.float64) - np.asarray(low, dtype=np.float64)
        return np.where(hl > 0, (np.asarray(close, dtype=np.float64) - np.asarray(open_, dtype=np.float64)) / hl, 0.0)

    @staticmethod
    def linear_regression_slope(close: np.ndarray, period: int = 14) -> np.ndarray:
        """48. Linear Regression Slope."""
        close = np.asarray(close, dtype=np.float64)
        n = len(close)
        slope = np.full(n, np.nan)
        if n < period:
            return slope
        x = np.arange(period, dtype=np.float64)
        x_mean = np.mean(x)
        x_dev = x - x_mean
        denom = np.sum(x_dev ** 2)

        for i in range(period - 1, n):
            y = close[i - period + 1:i + 1]
            slope[i] = np.sum(x_dev * (y - np.mean(y))) / denom
        return slope

    @staticmethod
    def vroc(volume: np.ndarray, period: int = 14) -> np.ndarray:
        """49. Volume Rate of Change (VROC)."""
        vol = np.asarray(volume, dtype=np.float64)
        res = np.full_like(vol, np.nan)
        if len(vol) > period:
            denom = vol[:-period]
            res[period:] = np.where(denom > 0, 100.0 * (vol[period:] - denom) / denom, 0.0)
        return res

    @staticmethod
    def fractal_chaos_bands(high: np.ndarray, low: np.ndarray, period: int = 5) -> Dict[str, np.ndarray]:
        """50. Fractal Chaos Bands (FCB)."""
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        n = len(high)
        fcb_high = np.full(n, np.nan)
        fcb_low = np.full(n, np.nan)

        for i in range(2, n - 2):
            if high[i] > high[i - 1] and high[i] > high[i - 2] and high[i] > high[i + 1] and high[i] > high[i + 2]:
                fcb_high[i:] = high[i]
            if low[i] < low[i - 1] and low[i] < low[i - 2] and low[i] < low[i + 1] and low[i] < low[i + 2]:
                fcb_low[i:] = low[i]

        return {"upper": fcb_high, "lower": fcb_low}

    @staticmethod
    def kaufman_efficiency_ratio(close: np.ndarray, period: int = 14) -> np.ndarray:
        """51. Kaufman Efficiency Ratio (KER). Numba JIT accelerated."""
        arr = np.ascontiguousarray(close, dtype=np.float64)
        return _kaufman_efficiency_ratio_kernel(arr, int(period))

    @staticmethod
    def ultimate_oscillator(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        p1: int = 7,
        p2: int = 14,
        p3: int = 28
    ) -> np.ndarray:
        """52. Ultimate Oscillator (UO)."""
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        n = len(close)
        if n < p3 + 1:
            return np.full(n, np.nan)

        prev_close = close[:-1]
        bp = close[1:] - np.minimum(low[1:], prev_close)
        tr = np.maximum(high[1:], prev_close) - np.minimum(low[1:], prev_close)

        uo = np.full(n, np.nan)
        for i in range(p3 - 1, len(bp)):
            avg1 = np.sum(bp[i - p1 + 1:i + 1]) / np.sum(tr[i - p1 + 1:i + 1]) if np.sum(tr[i - p1 + 1:i + 1]) > 0 else 0.0
            avg2 = np.sum(bp[i - p2 + 1:i + 1]) / np.sum(tr[i - p2 + 1:i + 1]) if np.sum(tr[i - p2 + 1:i + 1]) > 0 else 0.0
            avg3 = np.sum(bp[i - p3 + 1:i + 1]) / np.sum(tr[i - p3 + 1:i + 1]) if np.sum(tr[i - p3 + 1:i + 1]) > 0 else 0.0
            uo[i + 1] = 100.0 * (4.0 * avg1 + 2.0 * avg2 + avg3) / 7.0
        return uo

    @classmethod
    def standard_deviation_bands(cls, close: np.ndarray, period: int = 20, num_std: float = 2.0) -> Dict[str, np.ndarray]:
        """53. Standard Deviation Bands."""
        sma_val = cls.sma(close, period)
        close = np.asarray(close, dtype=np.float64)
        n = len(close)
        upper = np.full(n, np.nan)
        lower = np.full(n, np.nan)
        for i in range(period - 1, n):
            std = np.std(close[i - period + 1:i + 1])
            upper[i] = sma_val[i] + num_std * std
            lower[i] = sma_val[i] - num_std * std
        return {"middle": sma_val, "upper": upper, "lower": lower}

    @staticmethod
    def kase_peak_oscillator(high: np.ndarray, low: np.ndarray, period: int = 14) -> np.ndarray:
        """54. Kase Peak Oscillator."""
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        n = len(high)
        kpo = np.full(n, np.nan)
        for i in range(period - 1, n):
            r_high = np.max(high[i - period + 1:i + 1]) - low[i]
            r_low = high[i] - np.min(low[i - period + 1:i + 1])
            kpo[i] = r_high - r_low
        return kpo

    @staticmethod
    def hurst_exponent(close: np.ndarray, max_lags: int = 20) -> float:
        """
        55. Hurst Exponent (H). Numba JIT accelerated.
        H > 0.55: Trending regime
        H < 0.45: Mean-reverting regime
        0.45 <= H <= 0.55: Choppy noise regime
        """
        arr = np.ascontiguousarray(close, dtype=np.float64)
        return _hurst_exponent_kernel(arr, int(max_lags))


# Global singleton instance
indicators = TechnicalIndicators()
