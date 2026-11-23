"""Independent realized-factor attribution (training only in the study CLI)."""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from marketneutral_equity.engine import Engine
from marketneutral_equity.strategy import CandidateStrategy
from marketneutral_equity.strategy_baseline import SimpleReversalBaseline
from marketneutral_equity.diagnostics import factor_loadings,reconcile_trades

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--strategy",choices=("candidate","baseline"),default="candidate")
    ap.add_argument("--split",choices=("train","validation","test"),default="train")
    ap.add_argument("--out",default="outputs/factor_diagnostics.json")
    a=ap.parse_args()
    engine=Engine(ROOT/"data")
    strat=CandidateStrategy() if a.strategy=="candidate" else SimpleReversalBaseline()
    result=engine.run(strat,split=a.split)
    factors=[engine.factor_by_date[row["date"]] for row in result["daily"]]
    diagnosis=factor_loadings(result["daily"],factors,engine.meta)
    diagnosis["pnl_execution_reconciliation"]=reconcile_trades(result["trades"],result["daily"])
    diagnosis["strategy"]=a.strategy;diagnosis["split"]=a.split
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(diagnosis,indent=2),encoding="utf-8")
    print(json.dumps(diagnosis,indent=2))
