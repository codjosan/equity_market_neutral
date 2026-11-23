"""Point-in-time, split and market-data audit. Offline; nonzero exit on errors."""
from pathlib import Path
from collections import Counter
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from marketneutral_equity.data import load_dataset


def audit(directory):
    dates,bars,factors,hist,universe=load_dataset(directory)
    manifest=json.loads((Path(directory)/"manifest.json").read_text(encoding="utf-8"))
    errors=[]
    count=Counter()
    for ds in dates:
        if set(bars[ds])!=set(universe):errors.append("Missing/duplicate name: "+ds)
        f=factors.get(ds)
        if not f:errors.append("Missing factor date: "+ds)
        else:count[f["split"]]+=1
        for name,row in bars[ds].items():
            if row["date"]!=ds:errors.append("Mismatched date: "+ds+"/"+name)
            if f and row["split"]!=f["split"]:errors.append("Split mismatch: "+ds+"/"+name)
            if not (0<row["low"]<=min(row["open"],row["close"])
                    and row["high"]>=max(row["open"],row["close"])):
                errors.append("Impossible OHLC: "+ds+"/"+name)
            if row["adv_usd"]<=0 or row["spread_bps"]<0:
                errors.append("Invalid liquidity: "+ds+"/"+name)
            if row["borrow_rate_annual"]<0:
                errors.append("Invalid stock loan rate: "+ds+"/"+name)
    if len(dates)!=manifest["trading_days"]:errors.append("Wrong number of dates")
    if len(universe)!=manifest["assets"]:errors.append("Wrong number of assets")
    if dict(count)!=manifest["split_days"]:errors.append("Unexpected partition counts")
    if dates!=sorted(dates):errors.append("Unsorted dates")
    result={"days":len(dates),"names":len(universe),"rows":len(dates)*len(universe),
            "split_days":dict(count),"errors":errors[:30],"error_count":len(errors)}
    print(json.dumps(result,indent=2))
    if errors:sys.exit(1)
    return result

if __name__=="__main__":audit(ROOT/"data")
