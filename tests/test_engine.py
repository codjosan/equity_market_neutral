import tempfile
import unittest
from pathlib import Path
from fixtures import tiny_data
from marketneutral_equity.engine import Engine, EngineConfig
from marketneutral_equity.metrics import summarize, objective_failures
from marketneutral_equity.strategy import CandidateStrategy
from marketneutral_equity.strategy_baseline import SimpleReversalBaseline

ROOT=Path(__file__).resolve().parents[1]

class Balanced:
    def on_day(self, context):
        return {"A":0.02,"B":-0.02}

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data=tiny_data(self.tmp.name)

    def test_full_dataset_size(self):
        engine=Engine(ROOT/"data")
        self.assertEqual(len(engine.dates),504)
        self.assertEqual(len(engine.meta),48)

    def test_candidate_stub_cannot_pass_flat_gate(self):
        m=summarize(Engine(self.data).run(CandidateStrategy(),split="train"))
        self.assertEqual(m["trade_count"],0)
        self.assertIn("degenerate_flat_strategy",objective_failures(m))

    def test_no_fills_on_signal_date(self):
        r=Engine(self.data).run(Balanced(),split="train")
        self.assertTrue(r["trades"])
        self.assertEqual(r["trades"][0]["date"],"2026-01-02")

    def test_context_has_no_future_or_split(self):
        class Inspector:
            def on_day(self,ctx):
                assert not hasattr(ctx,"split")
                assert len(ctx.factor_history)==len(ctx.history["A"])
                assert all(r["date"]<=ctx.date for hist in ctx.history.values() for r in hist)
                assert all("split" not in r for r in ctx.factor_history)
                assert all("split" not in r for hist in ctx.history.values() for r in hist)
                assert all("split" not in r for r in ctx.bars.values())
                return {}
        r=Engine(self.data).run(Inspector())
        self.assertEqual(r["events"].get("strategy_exception",0),0)

    def test_future_open_does_not_change_current_decision(self):
        class Observe:
            def __init__(self):self.observed=[]
            def on_day(self,ctx):
                self.observed.append(ctx.bars["A"]["close"])
                return {}
        first=Observe();second=Observe()
        Engine(self.data).run(first,split="train")
        with tempfile.TemporaryDirectory() as d:
            path=tiny_data(d,modify=lambda day,s,row:row.update({"open":9000}) if day==2 and s=="A" else None)
            Engine(path).run(second,split="train")
        self.assertEqual(first.observed,second.observed)

    def test_pnl_reconciliation_every_day(self):
        r=Engine(self.data).run(Balanced(),split="train")
        m=summarize(r)
        self.assertTrue(m["pnl_reconciliation_passed"])
        self.assertTrue(all(abs(x["pnl_reconciliation_error"])<0.01 for x in r["daily"]))

    def test_cash_and_shares_overnight_pnl(self):
        r=Engine(self.data).run(Balanced(),split="train")
        d=r["daily"]
        self.assertEqual(d[0]["net_pnl"],0.0)
        self.assertGreater(d[1]["intraday_price_pnl"],0.0)
        self.assertNotEqual(d[2]["overnight_price_pnl"],0.0)

    def test_cannot_submit_nonfinite_weights(self):
        class Bad:
            def on_day(self,ctx):return {"A":float("nan")}
        r=Engine(self.data).run(Bad(),split="train")
        self.assertGreater(r["events"].get("invalid_target_nonfinite_position",0),0)
        self.assertEqual(len(r["trades"]),0)

    def test_cannot_submit_unknown_symbol(self):
        class Bad:
            def on_day(self,ctx):return {"GHOST":0.02}
        r=Engine(self.data).run(Bad(),split="train")
        self.assertGreater(r["events"].get("unknown_symbol",0),0)
        self.assertEqual(len(r["trades"]),0)

    def test_gross_or_net_target_invalid(self):
        class Bad:
            def on_day(self,ctx):return {"A":0.05,"B":0.05}
        r=Engine(self.data).run(Bad(),split="train")
        self.assertGreater(r["events"].get("invalid_target_net_limit",0),0)

    def test_protected_halt_and_stale_no_fills(self):
        with tempfile.TemporaryDirectory() as d:
            path=tiny_data(d,modify=lambda day,s,r:r.update({"halted":1}) if day==1 and s=="A" else None)
            engine=Engine(path)
            r=engine.run(Balanced(),split="train")
            self.assertFalse(any(t["date"]=="2026-01-02" and t["symbol"]=="A" for t in r["trades"]))
            self.assertGreater(r["events"].get("blocked_halt_stale",0),0)

    def test_no_new_short_without_locate(self):
        with tempfile.TemporaryDirectory() as d:
            path=tiny_data(d,modify=lambda day,s,r:r.update({"borrow_available":0}) if day==1 and s=="B" else None)
            r=Engine(path).run(Balanced(),split="train")
            self.assertFalse(any(t["date"]=="2026-01-02" and t["symbol"]=="B" and t["side"]=="sell" for t in r["trades"]))
            self.assertGreater(r["events"].get("short_locate_block",0),0)

    def test_recall_forced_buyin(self):
        with tempfile.TemporaryDirectory() as d:
            path=tiny_data(d,modify=lambda day,s,r:r.update({"borrow_available":0}) if day>=2 and s=="B" else None)
            r=Engine(path).run(Balanced(),split="train")
            self.assertTrue(any(t["forced_buyin"] and t["symbol"]=="B" for t in r["trades"]))

    def test_halt_delays_forced_buyin(self):
        with tempfile.TemporaryDirectory() as d:
            def change(day,s,row):
                if s=="B" and day>=2:row["borrow_available"]=0
                if s=="B" and day==2:row["halted"]=1
            path=tiny_data(d,modify=change)
            r=Engine(path).run(Balanced(),split="train")
            self.assertGreater(r["events"].get("unresolved_borrow_recall",0),0)
            self.assertTrue(any(t["forced_buyin"] and t["date"]=="2026-01-04" for t in r["trades"]))

    def test_partial_fills_preserve_portfolio_limit(self):
        with tempfile.TemporaryDirectory() as d:
            path=tiny_data(d,modify=lambda day,s,r:r.update({"adv_usd":200}) if day==1 and s=="B" else None)
            r=Engine(path).run(Balanced(),split="train")
            self.assertGreater(r["events"].get("partial_fill",0),0)
            self.assertLessEqual(abs(r["daily"][1]["net_exposure"]),0.0301)

    def test_split_evaluation_no_train_trades_in_validation(self):
        r=Engine(self.data).run(Balanced(),split="validation")
        self.assertTrue(r["trades"])
        self.assertTrue(all(t["date"]>="2026-01-05" for t in r["trades"]))
        self.assertEqual(len(r["daily"]),2)

    def test_strategy_error_does_not_crash_evaluator(self):
        class Crash:
            def on_day(self,ctx):raise RuntimeError("bad")
        r=Engine(self.data).run(Crash(),split="train")
        self.assertGreater(r["events"].get("strategy_exception",0),0)

if __name__=="__main__":unittest.main()
