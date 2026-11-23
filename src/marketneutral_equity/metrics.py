"""Transparent net-return, risk, and accounting metrics for isolated splits."""
from math import sqrt


def summarize(result):
    rows=result["daily"]
    if not rows:
        raise ValueError("Cannot summarize an empty backtest")
    starting=rows[0]["start_equity"]
    ending=rows[-1]["equity"]
    rets=[r["net_pnl"]/max(1.0,r["start_equity"]) for r in rows]
    mean=sum(rets)/len(rets)
    variance=sum((r-mean)**2 for r in rets)/max(1,len(rets)-1)
    sigma=sqrt(variance)
    peak=starting
    max_dd=0.0
    for row in rows:
        peak=max(peak,row["equity"])
        max_dd=max(max_dd,1-row["equity"]/peak)
    totals={
        "overnight_price_pnl_usd":sum(r["overnight_price_pnl"] for r in rows),
        "intraday_price_pnl_usd":sum(r["intraday_price_pnl"] for r in rows),
        "commission_usd":sum(r["commission"] for r in rows),
        "spread_cost_usd":sum(r["spread_cost"] for r in rows),
        "impact_cost_usd":sum(r["impact_cost"] for r in rows),
        "borrow_cost_usd":sum(r["borrow_cost"] for r in rows),
        "turnover_usd":sum(r["turnover_usd"] for r in rows),
        "net_pnl_usd":sum(r["net_pnl"] for r in rows),
    }
    implied=(totals["overnight_price_pnl_usd"]+totals["intraday_price_pnl_usd"]
             -totals["commission_usd"]-totals["spread_cost_usd"]
             -totals["impact_cost_usd"]-totals["borrow_cost_usd"])
    reconciliation_error=totals["net_pnl_usd"]-implied
    return {
        "split":result["split"],"scenario":result["scenario"],
        "days":len(rows),"start_equity":round(starting,2),
        "end_equity":round(ending,2),
        "net_return_pct":round(100*(ending/starting-1),5),
        "max_drawdown_pct":round(100*max_dd,5),
        "sharpe":round(mean/sigma*sqrt(252),5) if sigma>1e-12 else 0.0,
        "annualized_vol_pct":round(sigma*sqrt(252)*100,5),
        "trade_count":len(result["trades"]),
        "nonzero_position_days":sum(r["gross_exposure"]>1e-5 for r in rows),
        "avg_gross_exposure":round(sum(r["gross_exposure"] for r in rows)/len(rows),6),
        "max_gross_exposure":round(max(r["gross_exposure"] for r in rows),6),
        "max_abs_net_exposure":round(max(abs(r["net_exposure"]) for r in rows),6),
        "max_name_exposure":round(max(r["max_name_weight"] for r in rows),6),
        "max_sector_net_exposure":round(max(r["max_sector_net"] for r in rows),6),
        "risk_exception_days":sum(r["risk_issue_count"]>0 for r in rows),
        "pnl_reconciliation_error_usd":round(reconciliation_error,6),
        "pnl_reconciliation_passed":abs(reconciliation_error)<max(0.02,abs(ending)*1e-8),
        "events":result["events"],
        "attribution":{k:round(v,3) for k,v in totals.items()},
        "limitations":["Synthetic historical data", "Close-to-next-open signal timing", 
                       "Simplified auction and stock-borrow pricing", 
                       "Final holdings marked to market without an exit auction"],
    }


def objective_failures(m, *, min_trades=12, require_profit=True):
    """Completion gates; do not treat safe cash-only portfolios as success."""
    failures=[]
    if m["trade_count"]<min_trades:
        failures.append("insufficient_actual_fills")
    if m["nonzero_position_days"]<10:
        failures.append("degenerate_flat_strategy")
    if require_profit and m["net_return_pct"]<=0:
        failures.append("nonpositive_net_return")
    if m["max_drawdown_pct"]>10:
        failures.append("drawdown_above_10pct")
    if m["max_gross_exposure"]>1.5001:
        failures.append("gross_limit")
    if m["max_abs_net_exposure"]>0.0301:
        failures.append("net_limit")
    if m["max_name_exposure"]>0.0501:
        failures.append("name_limit")
    if m["max_sector_net_exposure"]>0.0801:
        failures.append("sector_limit")
    if not m["pnl_reconciliation_passed"]:
        failures.append("pnl_reconciliation_failed")
    if m["events"].get("pnl_reconciliation_failed",0):
        failures.append("daily_pnl_reconciliation_failed")
    if m["events"].get("strategy_exception",0):
        failures.append("strategy_crashed")
    return failures
