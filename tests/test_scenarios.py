import unittest
import tempfile
from fixtures import tiny_data
from marketneutral_equity.scenarios import Scenario,stress_cases,scenario_by_name
from marketneutral_equity.engine import Engine

class TwoSided:
    def on_day(self,c):return {"A":.025,"B":-.025}

class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=tiny_data(self.tmp.name)
    def test_scenarios_are_unique(self):
        names=[s.name for s in stress_cases()]
        self.assertEqual(len(names),len(set(names)))
        self.assertGreaterEqual(len(names),12)
    def test_default_scenario_identity(self):
        bar=Engine(self.path).by_date["2026-01-02"]["A"]
        self.assertEqual(Scenario().apply(bar,"A","TECH",1),bar)
    def test_invalid_multiplier_rejected(self):
        with self.assertRaises(ValueError):Scenario(spread_multiplier=-1)
    def test_outage_blocks_new_auction_fills(self):
        s=Scenario("outage",outage_symbols=("A",),outage_start=1,outage_end=1)
        r=Engine(self.path,scenario=s).run(TwoSided(),split="train")
        self.assertFalse(any(t["date"]=="2026-01-02" and t["symbol"]=="A" for t in r["trades"]))
    def test_auction_rejection_is_deterministic(self):
        s=Scenario("reject",rejection_modulus=2)
        a=Engine(self.path,scenario=s).run(TwoSided(),split="train")
        b=Engine(self.path,scenario=s).run(TwoSided(),split="train")
        self.assertEqual(a["trades"],b["trades"])
        self.assertGreater(a["events"].get("auction_rejection",0),0)
    def test_sector_shock_persists(self):
        base=Engine(self.path).by_date["2026-01-03"]["A"]
        out=Scenario("shock",shock_sector="TECH",shock_start=2,shock_return=-.2)
        altered=out.apply(base,"A","TECH",3)
        self.assertAlmostEqual(altered["close"],.8*base["close"])
        self.assertEqual(out.apply(base,"C","ENERGY",3)["close"],base["close"])
    def test_extreme_costs_cannot_create_positive_trade_cost(self):
        s=Scenario("cost",spread_multiplier=4,impact_multiplier=4)
        r=Engine(self.path,scenario=s).run(TwoSided(),split="train")
        self.assertTrue(all(t["commission_usd"]>=0 and t["impact_cost_usd"]>=0 for t in r["trades"]))
    def test_unknown_scenario_error(self):
        with self.assertRaises(ValueError):scenario_by_name("does_not_exist")

if __name__=="__main__":unittest.main()
