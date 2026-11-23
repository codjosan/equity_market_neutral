"""Portfolio constraints and observable ex-ante factor risk utilities.

Only past public returns and market factors may enter a signal. True asset
betas, hidden regime metadata, and split labels are NOT part of this module.
"""
from collections import defaultdict
from math import isfinite, sqrt

LIMIT_EPS = 1e-8


def portfolio_exposures(weights, meta, beta=None):
    by_sector = defaultdict(float)
    by_sector_gross = defaultdict(float)
    for symbol, weight in weights.items():
        w = float(weight)
        by_sector[meta[symbol]["sector"]] += w
        by_sector_gross[meta[symbol]["sector"]] += abs(w)
    return {
        "gross": sum(abs(w) for w in weights.values()),
        "net": sum(weights.values()),
        "max_name": max((abs(w) for w in weights.values()), default=0.0),
        "sector_net": dict(by_sector),
        "sector_gross": dict(by_sector_gross),
        "beta_net": sum(weights[s] * beta.get(s, 0.0) for s in weights) if beta else None,
    }


def constraint_violations(weights, meta, cfg, *, tolerance=LIMIT_EPS):
    if set(weights) != set(meta):
        return ["missing_or_unknown_symbols"]
    if any(not isfinite(w) for w in weights.values()):
        return ["nonfinite_position"]
    x = portfolio_exposures(weights, meta)
    issues = []
    if x["gross"] > cfg.max_gross + tolerance:
        issues.append("gross_limit")
    if abs(x["net"]) > cfg.max_abs_net + tolerance:
        issues.append("net_limit")
    if x["max_name"] > cfg.max_abs_position + tolerance:
        issues.append("name_limit")
    if any(abs(w) > cfg.max_abs_sector_net+tolerance for w in x["sector_net"].values()):
        issues.append("sector_limit")
    return issues


def rolling_beta(asset_returns, factor_returns, min_points=30):
    """OLS beta using aligned historical observations. No intercept bias.

    Inputs must be of equal length and explicitly end before decision date or
    with factors already published by decision time.
    """
    if len(asset_returns) != len(factor_returns):
        raise ValueError("Returns and factors are not aligned")
    if len(asset_returns) < min_points:
        return None
    x_mean = sum(factor_returns)/len(factor_returns)
    y_mean = sum(asset_returns)/len(asset_returns)
    variance = sum((x-x_mean)**2 for x in factor_returns)
    if variance < 1e-12:
        return None
    cov = sum((x-x_mean)*(y-y_mean) for x,y in zip(factor_returns,asset_returns))
    return cov/variance


def daily_returns(closes):
    return [closes[i]/closes[i-1]-1.0 for i in range(1,len(closes)) if closes[i-1] > 0]


def estimate_betas(history, factor_history, lookback=80, min_points=30):
    """Estimate each asset's broad-market beta from point-in-time observations.

    `factor_history` MUST contain every factor date through the decision date.
    Matching by ISO date is crucial when rows go missing. Missing asset/factor
    observations are skipped, never backfilled from the future.
    """
    factors = {r["date"]:r["market_return"] for r in factor_history}
    result = {}
    for symbol, rows in history.items():
        points = []
        for old, new in zip(rows[:-1], rows[1:]):
            if new["date"] in factors and old["close"] > 0:
                points.append((new["close"]/old["close"]-1.0, factors[new["date"]]))
        points = points[-lookback:]
        if len(points) >= min_points:
            b = rolling_beta([p[0] for p in points], [p[1] for p in points], min_points)
            if b is not None and isfinite(b): result[symbol] = b
    return result


def shrink_to_market(betas, shrinkage=0.25):
    if not (0.0 <= shrinkage <= 1.0):
        raise ValueError("Invalid shrinkage")
    return {s:(1-shrinkage)*b+shrinkage for s,b in betas.items()}


def portfolio_beta(weights, betas):
    return sum(weights.get(s,0.0)*b for s,b in betas.items())


def covariance(x, y):
    if len(x)!=len(y) or len(x)<2:
        raise ValueError("At least two aligned samples required")
    mx=sum(x)/len(x); my=sum(y)/len(y)
    return sum((a-mx)*(b-my) for a,b in zip(x,y))/(len(x)-1)


def annualized_vol(returns):
    if len(returns)<2: return 0.0
    return sqrt(max(0.0,covariance(returns,returns))*252)
