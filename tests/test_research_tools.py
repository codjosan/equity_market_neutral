import math
import unittest
from marketneutral_equity.risk import (rolling_beta, estimate_betas, daily_returns,
    portfolio_exposures, constraint_violations, covariance, annualized_vol)
from marketneutral_equity.engine import EngineConfig
from marketneutral_equity.research_tools import (percentile, winsorize, robust_zscores,
    sector_demean, trailing_return, volatility_from_prices, inverse_vol_weight,
    normalize_long_short, enforce_borrow_liquidity, neutralize_beta,
    neutralize_sector, moving_block_bootstrap, no_trade_band, rebalance_cost_estimate)

class ResearchUnitTests(unittest.TestCase):
    def setUp(self):
        self.meta={"A":{"sector":"TECH"},"B":{"sector":"TECH"},
                   "C":{"sector":"ENERGY"},"D":{"sector":"ENERGY"}}
    def test_factor_beta_exact(self):
        x=[(i-10)/100 for i in range(30)]
        y=[2*z+0.01 for z in x]
        self.assertAlmostEqual(rolling_beta(y,x),2,places=9)

    def test_factor_misalignment_rejected(self):
        with self.assertRaises(ValueError):rolling_beta([0,1],[0])

    def test_factor_constant_variance(self):
        self.assertIsNone(rolling_beta(list(range(50)),[0.02]*50))

    def test_estimate_betas_matches_dates_only(self):
        h={"A":[{"date":f"2026-01-{i:02d}","close":100+i} for i in range(1,32)]}
        factors=[{"date":f"2026-01-{i:02d}","market_return":0.001*i} for i in range(2,32)]
        estimate=estimate_betas(h,factors,min_points=20)
        self.assertIn("A",estimate)
        self.assertTrue(math.isfinite(estimate["A"]))

    def test_portfolio_violations_detect_all(self):
        weights={"A":.05,"B":.05,"C":.05,"D":.05}
        self.assertIn("net_limit",constraint_violations(weights,self.meta,EngineConfig()))
        self.assertIn("sector_limit",constraint_violations(weights,self.meta,EngineConfig()))

    def test_sector_neutralization(self):
        result=neutralize_sector({"A":.03,"B":-.01,"C":.08,"D":.02},self.meta)
        self.assertAlmostEqual(result["A"]+result["B"],0)
        self.assertAlmostEqual(result["C"]+result["D"],0)

    def test_beta_neutralization_approximate(self):
        weights={"A":.02,"B":-.02,"C":0.01,"D":-.01}
        betas={"A":1,"B":.8,"C":1.5,"D":.9}
        new=neutralize_beta(weights,betas)
        self.assertLess(abs(sum(new[s]*betas[s] for s in new)),abs(sum(weights[s]*betas[s] for s in weights)))

    def test_symmetric_long_short(self):
        scores={"A":-3,"B":-1,"C":2,"D":3}
        w=normalize_long_short(scores,gross=.8)
        self.assertAlmostEqual(sum(w.values()),0)
        self.assertAlmostEqual(sum(abs(x) for x in w.values()),.8)

    def test_normalize_flat_when_no_shorts(self):
        self.assertTrue(all(v==0 for v in normalize_long_short({"A":1,"B":2}).values()))

    def test_no_trade_band_reuses_existing(self):
        out=no_trade_band({"A":.031,"B":-.02},{"A":.03,"B":0},band=.002)
        self.assertAlmostEqual(out["A"],.03)
        self.assertAlmostEqual(out["B"],-.02)

    def test_volatility_warmup(self):
        self.assertIsNone(volatility_from_prices([{"close":100}]*2,days=20))
        self.assertAlmostEqual(volatility_from_prices([{"close":100}]*30,days=20),0)

    def test_trailing_return_no_lookahead(self):
        rows=[{"close":x} for x in (100,101,102,103,120)]
        self.assertAlmostEqual(trailing_return(rows,3,skip_recent=1),.03)
        self.assertAlmostEqual(trailing_return(rows,3,skip_recent=0),120/101-1)

    def test_robust_zscores_ignore_inf(self):
        z=robust_zscores({"A":-3,"B":0,"C":4,"D":float("nan")})
        self.assertTrue(all(math.isfinite(x) for x in z.values()))
        self.assertEqual(z["D"],0)

    def test_winsorize_clamps_outliers(self):
        result=winsorize([0,1,2,3,1000],.20,.80)
        self.assertLess(result[-1],1000)

    def test_cost_estimate_nonnegative(self):
        bars={s:{"adv_usd":1e7,"spread_bps":10} for s in self.meta}
        self.assertGreater(rebalance_cost_estimate({"A":.05},{"A":0},bars),0)

    def test_bootstrap_deterministic(self):
        x=[0.01,-0.003,0.001,0.002,-.009]*7
        a=moving_block_bootstrap(x,block_size=5,draws=25,seed=21)
        b=moving_block_bootstrap(x,block_size=5,draws=25,seed=21)
        self.assertEqual(a,b)
        self.assertEqual(len(a),25)

    def test_borrow_liquidity_filter(self):
        bars={s:{"halted":False,"stale":False,"adv_usd":3e6,
                 "borrow_available":(s!="B")} for s in self.meta}
        w=enforce_borrow_liquidity({"A":.1,"B":-.02,"C":.02,"D":-.02},bars)
        self.assertEqual(w["B"],0)
        self.assertEqual(w["A"],.035)

    def test_covariance_and_vol(self):
        self.assertGreater(covariance([1,2,3],[2,4,6]),0)
        self.assertGreater(annualized_vol([-.01,0,.01]),0)

if __name__=="__main__":unittest.main()
