"""Post-trade factor audit: realized loadings, accounting and risk regimes."""
from math import sqrt
from .risk import rolling_beta
from .research_tools import percentile


def factor_loadings(daily, factor_rows, universe):
    """Single-factor OLS slopes for strategy against market and sectors.

    This diagnostic deliberately uses **realized** strategy returns and should
    never be supplied back into a signal at an earlier point in time.
    """
    factors={row["date"]:row for row in factor_rows}
    rows=[row for row in daily if row["date"] in factors]
    if len(rows)<30:
        return {"observations":len(rows),"loadings":{},"warnings":["Insufficient daily observations"]}
    y=[r["net_pnl"]/max(1.0,r["start_equity"]) for r in rows]
    names=[k for k in factors[rows[0]["date"]] if k.endswith("_return")]
    loadings={}
    for name in names:
        x=[factors[r["date"]][name] for r in rows]
        coefficient=rolling_beta(y,x,min_points=30)
        loadings[name]=round(coefficient,6) if coefficient is not None else None
    turnover=sum(row["turnover_usd"] for row in rows)
    gross=sum(row["gross_exposure"] for row in rows)/len(rows)
    return {
        "observations":len(rows),"loadings":loadings,
        "avg_gross":gross,"turnover_usd":turnover,
        "gross_return_pct_before_costs":100*sum(
            r["overnight_price_pnl"]+r["intraday_price_pnl"] for r in rows
        )/max(1,rows[0]["start_equity"]),
        "net_return_pct_approx":100*sum(r["net_pnl"] for r in rows)/max(1,rows[0]["start_equity"]),
        "max_daily_loss_pct":100*min(y),
        "daily_return_5th_pctile_pct":100*percentile(y,0.05),
        "warnings":["Post-trade factor regression is descriptive, not ex-ante neutrality proof",
                    "Coefficients are univariate; correlated sectors can confound interpretation"],
    }


def reconcile_trades(trades, daily):
    total_commissions=sum(t["commission_usd"] for t in trades)
    total_spread=sum(t["spread_cost_usd"] for t in trades)
    total_impact=sum(t["impact_cost_usd"] for t in trades)
    return {
        "commission_error_usd":total_commissions-sum(d["commission"] for d in daily),
        "spread_error_usd":total_spread-sum(d["spread_cost"] for d in daily),
        "impact_error_usd":total_impact-sum(d["impact_cost"] for d in daily),
        "notes":"Per-trade costs rounded to four decimals; small rounding differences expected",
    }
