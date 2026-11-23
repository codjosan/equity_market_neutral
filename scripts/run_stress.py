"""Regenerate baseline stress matrix (strategy stays candidate by default)."""
from pathlib import Path
import json
import argparse
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from marketneutral_equity.runner import run
from marketneutral_equity.scenarios import stress_cases

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--strategy",choices=("baseline","candidate"),default="candidate")
    ap.add_argument("--split",choices=("train","validation","test"),default="validation")
    ap.add_argument("--out",default="outputs/stress_matrix.json")
    args=ap.parse_args()
    data=[]
    for scene in stress_cases():
        metrics=run(args.strategy,args.split,scene.name,str(ROOT/"data"))
        data.append({"scenario":scene.name,"metrics":metrics})
        print(scene.name,metrics["net_return_pct"],metrics["max_drawdown_pct"])
    result={"strategy":args.strategy,"split":args.split,"scenarios":data}
    out=ROOT/args.out
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("Wrote",out)
