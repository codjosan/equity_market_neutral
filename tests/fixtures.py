"""Tiny synthetic deterministic execution fixture for invariant-based tests."""
import csv
from pathlib import Path

SYMBOLS=("A","B","C","D")

def write_csv(path,fields,rows):
    with Path(path).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader();w.writerows(rows)


def tiny_data(folder, days=8, *, modify=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    universe=[{"symbol":s,"sector":"TECH" if i<2 else "ENERGY",
               "market_cap_usd":1e10} for i,s in enumerate(SYMBOLS)]
    write_csv(folder/"universe.csv",["symbol","sector","market_cap_usd"],universe)
    bars=[];factors=[]
    for day in range(days):
        ds=f"2026-01-{day+1:02d}"
        split="train" if day<4 else ("validation" if day<6 else "test")
        factors.append({"date":ds,"split":split,"market_return":0.01 if day%2 else -0.01,
                        "market_vol_proxy":.01,"sector_tech_return":0.003,
                        "sector_energy_return":-0.003})
        for i,s in enumerate(SYMBOLS):
            close=100.0+(day*3 if s=="A" else (-day if s=="B" else 0))
            op=close-1 if s=="A" else close
            bar={"date":ds,"symbol":s,"open":op,"high":max(op,close)+1,
                 "low":min(op,close)-1,"close":close,"volume":100000,
                 "adv_usd":10000000.0,"spread_bps":4.0,
                 "halted":0,"stale":0,"borrow_available":1,
                 "borrow_rate_annual":0.03,"split":split}
            if modify: modify(day,s,bar)
            bars.append(bar)
    write_csv(folder/"daily_bars.csv",
              ["date","symbol","open","high","low","close","volume","adv_usd",
               "spread_bps","halted","stale","borrow_available","borrow_rate_annual","split"],bars)
    write_csv(folder/"market_factors.csv",
              ["date","market_return","market_vol_proxy","sector_tech_return",
               "sector_energy_return","split"],factors)
    return folder
