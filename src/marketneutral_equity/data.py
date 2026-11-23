import csv
from pathlib import Path
from collections import defaultdict

def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_dataset(data_dir):
    data_dir = Path(data_dir)
    bars = read_csv(data_dir/"daily_bars.csv")
    factors = read_csv(data_dir/"market_factors.csv")
    universe = read_csv(data_dir/"universe.csv")
    by_date = defaultdict(dict)
    history = defaultdict(list)
    for row in bars:
        for key in ("open","high","low","close","volume","adv_usd","spread_bps","borrow_rate_annual"):
            row[key] = float(row[key])
        for key in ("halted","stale","borrow_available"):
            row[key] = bool(int(row[key]))
        by_date[row["date"]][row["symbol"]] = row
        history[row["symbol"]].append(row)
    factor_by_date = {}
    for row in factors:
        for k in list(row):
            if k not in ("date","split"):
                row[k] = float(row[k])
        factor_by_date[row["date"]] = row
    meta = {r["symbol"]: {"sector":r["sector"], "market_cap_usd":float(r["market_cap_usd"])} for r in universe}
    dates = sorted(by_date)
    return dates, by_date, factor_by_date, history, meta
