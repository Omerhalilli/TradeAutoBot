"""
Unit tests for 54 Technical Indicators suite.
"""

import unittest
import numpy as np
from autotrade.analytics.indicators import indicators, TechnicalIndicators


class TestTechnicalIndicators(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 100
        # Realistic random walk prices
        returns = np.random.normal(0.0002, 0.005, n)
        self.closes = np.cumprod(1.0 + returns) * 1.3000
        self.highs = self.closes + np.abs(np.random.normal(0, 0.002, n))
        self.lows = self.closes - np.abs(np.random.normal(0, 0.002, n))
        self.opens = np.roll(self.closes, 1)
        self.opens[0] = self.closes[0]
        self.vols = np.random.uniform(100, 1000, n)

    def test_moving_averages(self):
        sma = indicators.sma(self.closes, 14)
        self.assertEqual(len(sma), len(self.closes))
        self.assertFalse(np.isnan(sma[-1]))

        ema = indicators.ema(self.closes, 14)
        self.assertEqual(len(ema), len(self.closes))
        self.assertFalse(np.isnan(ema[-1]))

        wma = indicators.wma(self.closes, 14)
        self.assertEqual(len(wma), len(self.closes))
        self.assertFalse(np.isnan(wma[-1]))

        hma = indicators.hma(self.closes, 14)
        self.assertEqual(len(hma), len(self.closes))

        dema = indicators.dema(self.closes, 14)
        self.assertEqual(len(dema), len(self.closes))

        tema = indicators.tema(self.closes, 14)
        self.assertEqual(len(tema), len(self.closes))

        mcginley = indicators.mcginley_dynamic(self.closes, 14)
        self.assertEqual(len(mcginley), len(self.closes))
        self.assertFalse(np.isnan(mcginley[-1]))

    def test_oscillators_and_momentum(self):
        rsi = indicators.rsi(self.closes, 14)
        self.assertTrue(0.0 <= rsi[-1] <= 100.0)

        macd_dict = indicators.macd(self.closes, 12, 26, 9)
        self.assertIn("macd", macd_dict)
        self.assertIn("signal", macd_dict)
        self.assertIn("histogram", macd_dict)
        self.assertEqual(len(macd_dict["macd"]), len(self.closes))

        stoch = indicators.stochastic(self.highs, self.lows, self.closes)
        self.assertIn("fast_k", stoch)
        self.assertIn("slow_d", stoch)

        wpr = indicators.williams_r(self.highs, self.lows, self.closes)
        self.assertTrue(-100.0 <= wpr[-1] <= 0.0)

        cci = indicators.cci(self.highs, self.lows, self.closes)
        self.assertEqual(len(cci), len(self.closes))

        mom = indicators.momentum(self.closes, 14)
        self.assertFalse(np.isnan(mom[-1]))

        roc = indicators.roc(self.closes, 12)
        self.assertFalse(np.isnan(roc[-1]))

        cmo = indicators.cmo(self.closes, 14)
        self.assertTrue(-100.0 <= cmo[-1] <= 100.0)

        tsi = indicators.tsi(self.closes)
        self.assertEqual(len(tsi), len(self.closes))

        ao = indicators.awesome_oscillator(self.highs, self.lows)
        self.assertEqual(len(ao), len(self.closes))

        ac = indicators.accelerator_oscillator(self.highs, self.lows)
        self.assertEqual(len(ac), len(self.closes))

    def test_volatility_bands(self):
        atr = indicators.atr(self.highs, self.lows, self.closes, 14)
        self.assertGreater(atr[-1], 0.0)

        natr = indicators.natr(self.highs, self.lows, self.closes, 14)
        self.assertGreater(natr[-1], 0.0)

        bb = indicators.bollinger_bands(self.closes, 20, 2.0)
        self.assertTrue(bb["upper"][-1] >= bb["middle"][-1] >= bb["lower"][-1])

        kc = indicators.keltner_channels(self.highs, self.lows, self.closes)
        self.assertTrue(kc["upper"][-1] >= kc["middle"][-1] >= kc["lower"][-1])

        donchian = indicators.donchian_channels(self.highs, self.lows, 20)
        self.assertTrue(donchian["upper"][-1] >= donchian["lower"][-1])

        st = indicators.supertrend(self.highs, self.lows, self.closes)
        self.assertIn(st["direction"][-1], [1, -1])

        hv = indicators.historical_volatility(self.closes, 20)
        self.assertGreater(hv[-1], 0.0)

    def test_trend_and_directional(self):
        adx_res = indicators.adx(self.highs, self.lows, self.closes, 14)
        self.assertIn("adx", adx_res)
        self.assertIn("plus_di", adx_res)
        self.assertIn("minus_di", adx_res)

        ichimoku = indicators.ichimoku(self.highs, self.lows, self.closes)
        self.assertIn("tenkan_sen", ichimoku)
        self.assertIn("kijun_sen", ichimoku)

        sar = indicators.parabolic_sar(self.highs, self.lows)
        self.assertEqual(len(sar), len(self.highs))

        aroon = indicators.aroon(self.highs, self.lows, 25)
        self.assertTrue(0.0 <= aroon["aroon_up"][-1] <= 100.0)

        vortex = indicators.vortex(self.highs, self.lows, self.closes, 14)
        self.assertIn("plus_vi", vortex)

        elder = indicators.elder_ray(self.highs, self.lows, self.closes, 13)
        self.assertIn("bull_power", elder)

    def test_volume_indicators(self):
        obv = indicators.obv(self.closes, self.vols)
        self.assertEqual(len(obv), len(self.closes))

        vwap = indicators.vwap(self.highs, self.lows, self.closes, self.vols)
        self.assertEqual(len(vwap), len(self.closes))

        cmf = indicators.cmf(self.highs, self.lows, self.closes, self.vols)
        self.assertTrue(-1.0 <= cmf[-1] <= 1.0)

        mfi = indicators.mfi(self.highs, self.lows, self.closes, self.vols)
        self.assertTrue(0.0 <= mfi[-1] <= 100.0)

        fi = indicators.force_index(self.closes, self.vols)
        self.assertEqual(len(fi), len(self.closes))

        eom = indicators.eom(self.highs, self.lows, self.vols)
        self.assertEqual(len(eom), len(self.closes))

        pvt = indicators.pvt(self.closes, self.vols)
        self.assertEqual(len(pvt), len(self.closes))

    def test_structural_and_cycle_indicators(self):
        zigzag = indicators.zigzag(self.highs, self.lows, deviation_pct=0.3)
        self.assertIsInstance(zigzag, list)
        self.assertGreater(len(zigzag), 0)

        elliott = indicators.elliott_wave(self.highs, self.lows)
        self.assertIn("pattern", elliott)

        fib = indicators.fibonacci_levels(1.3500, 1.3000)
        self.assertIn("fib_382", fib)
        self.assertIn("fib_618", fib)

        pivots = indicators.pivot_points(1.3500, 1.3000, 1.3200)
        self.assertIn("pivot", pivots)
        self.assertIn("camarilla_h4", pivots)

        dpo = indicators.dpo(self.closes, 20)
        self.assertEqual(len(dpo), len(self.closes))

        coppock = indicators.coppock_curve(self.closes)
        self.assertEqual(len(coppock), len(self.closes))

        mass = indicators.mass_index(self.highs, self.lows)
        self.assertEqual(len(mass), len(self.highs))

        kst = indicators.kst(self.closes)
        self.assertIn("kst", kst)

        bop = indicators.balance_of_power(self.opens, self.highs, self.lows, self.closes)
        self.assertEqual(len(bop), len(self.closes))

        slope = indicators.linear_regression_slope(self.closes, 14)
        self.assertEqual(len(slope), len(self.closes))

        vroc = indicators.vroc(self.vols, 14)
        self.assertEqual(len(vroc), len(self.vols))

        fcb = indicators.fractal_chaos_bands(self.highs, self.lows)
        self.assertIn("upper", fcb)

        er = indicators.kaufman_efficiency_ratio(self.closes, 14)
        self.assertTrue(0.0 <= er[-1] <= 1.0)

        uo = indicators.ultimate_oscillator(self.highs, self.lows, self.closes)
        self.assertTrue(0.0 <= uo[-1] <= 100.0)

        sdb = indicators.standard_deviation_bands(self.closes, 20)
        self.assertIn("upper", sdb)

        kpo = indicators.kase_peak_oscillator(self.highs, self.lows)
        self.assertEqual(len(kpo), len(self.highs))

        h = indicators.hurst_exponent(self.closes)
        self.assertTrue(0.0 <= h <= 1.0)

    def test_market_structure_and_dynamic_kaufman(self):
        # 1. Dynamic Kaufman adaptive periods
        dk_res = indicators.compute_dynamic_kaufman_periods(self.closes)
        self.assertTrue(7 <= dk_res.rsi_period <= 28)
        self.assertTrue(10 <= dk_res.fast_ema_period <= 40)
        self.assertTrue(25 <= dk_res.slow_ema_period <= 90)
        self.assertTrue(0.0 <= dk_res.ker <= 1.0)

        # Test high-speed trend expansion
        trend_prices = np.linspace(100.0, 200.0, 50)
        dk_trend = indicators.compute_dynamic_kaufman_periods(trend_prices)
        self.assertTrue(dk_trend.is_high_speed)
        self.assertLessEqual(dk_trend.rsi_period, 9)
        self.assertLessEqual(dk_trend.fast_ema_period, 14)

        # Test low-speed consolidation
        flat_prices = np.array([100.0, 100.5, 99.8, 100.2, 100.1] * 10)
        dk_flat = indicators.compute_dynamic_kaufman_periods(flat_prices)
        self.assertTrue(dk_flat.is_low_speed)
        self.assertGreaterEqual(dk_flat.rsi_period, 18)
        self.assertGreaterEqual(dk_flat.fast_ema_period, 30)

        # 2. OTE levels
        ote = indicators.compute_ote_levels(self.highs, self.lows, self.closes, lookback=50)
        self.assertIn(ote.direction, (-1, 1))
        self.assertGreater(ote.range_span, 0.0)
        self.assertTrue(ote.swing_low <= ote.equilibrium_50 <= ote.swing_high)
        self.assertTrue(ote.ote_lower <= ote.ote_upper)

        # 3. Vectorized FVG Zones
        fvg = indicators.compute_fvg_zones(self.highs, self.lows, self.closes)
        self.assertEqual(len(fvg.indices), len(fvg.types))
        self.assertEqual(len(fvg.indices), len(fvg.tops))
        self.assertEqual(len(fvg.indices), len(fvg.bottoms))
        self.assertEqual(len(fvg.indices), len(fvg.mitigated))

        # 4. Liquidity Pools & Sweeps
        lp = indicators.compute_liquidity_pools(self.highs, self.lows, self.closes, self.opens)
        self.assertIsInstance(lp.has_bullish_sweep, bool)
        self.assertIsInstance(lp.has_bearish_sweep, bool)
        self.assertIn(lp.sweep_type, (-1, 0, 1))


if __name__ == "__main__":
    unittest.main()


