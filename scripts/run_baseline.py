"""Regenerate published reference baseline for all chronological splits."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from marketneutral_equity.runner import run

if __name__=="__main__":
    for split in ("train","validation","test"):
        summary=run("baseline",split, "base",str(ROOT/"data"), ROOT/"outputs"/f"baseline_{split}")
        print(split, json.dumps({k:summary[k] for k in ("net_return_pct","max_drawdown_pct","trade_count","objective_failures")},indent=2))
