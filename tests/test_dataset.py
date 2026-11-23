import unittest
from pathlib import Path
from marketneutral_equity.data import load_dataset

ROOT=Path(__file__).resolve().parents[1]

class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dates,cls.by_date,cls.factors,cls.history,cls.meta=load_dataset(ROOT/"data")
    def test_universe_48(self):self.assertEqual(len(self.meta),48)
    def test_calendar_504(self):self.assertEqual(len(self.dates),504)
    def test_consistent_symbols(self):
        syms=set(self.meta)
        self.assertTrue(all(set(day)==syms for day in self.by_date.values()))
    def test_positive_prices_and_valid_borrow_rate(self):
        self.assertTrue(all(row["close"]>0 and row["borrow_rate_annual"]>=0
                            for day in self.by_date.values() for row in day.values()))
    def test_chronological_partitions(self):
        splits=[self.factors[d]["split"] for d in self.dates]
        self.assertEqual(splits.count("train"),252)
        self.assertEqual(splits.count("validation"),84)
        self.assertEqual(splits.count("test"),168)
        self.assertEqual(splits,sorted(splits,key={"train":0,"validation":1,"test":2}.get))
    def test_ohlc_range_encloses_open_close(self):
        rows=[r for bars in self.by_date.values() for r in bars.values()]
        self.assertTrue(all(r["high"]>=max(r["open"],r["close"])
                            and r["low"]<=min(r["open"],r["close"])
                            for r in rows))

    def test_borrow_and_stale_events_present(self):
        rows=[r for bars in self.by_date.values() for r in bars.values()]
        self.assertTrue(any(not r["borrow_available"] for r in rows))
        self.assertTrue(any(r["halted"] for r in rows))
        self.assertTrue(any(r["stale"] for r in rows))

if __name__=="__main__":unittest.main()
