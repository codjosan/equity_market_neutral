"""Reusable offline primitives for point-in-time equity alpha research.

These functions provide standard cross-sectional transformations, portfolio
neutralization helpers, and cost/bootstrap utilities for use in
strategy.py or modules under candidate/.
"""
from collections import defaultdict
from math import sqrt, isfinite
import random
from statistics import median

from .risk import portfolio_exposures


def percentile(values, q):
    if not values or not 0 <= q <= 1:
        raise ValueError("Empty vector or invalid quantile")
    xs=sorted(values)
    loc=(len(xs)-1)*q
    a=int(loc);b=min(len(xs)-1,a+1)
    return xs[a]+(loc-a)*(xs[b]-xs[a])


def winsorize(values, low=0.025, high=0.975):
    if not 0<=low<high<=1:
        raise ValueError("Invalid winsor bounds")
    lo,hi=percentile(values,low),percentile(values,high)
    return [min(hi,max(lo,x)) for x in values]


def robust_zscores(mapping, *, clip=4.0):
    if not mapping:return {}
    values=[v for v in mapping.values() if isfinite(v)]
    if not values:return {k:0.0 for k in mapping}
    med=median(values)
    dev=median([abs(v-med) for v in values])
    scale=max(1e-9,1.4826*dev)
    return {k:max(-clip,min(clip,(v-med)/scale)) if isfinite(v) else 0.0
            for k,v in mapping.items()}


def sector_demean(scores, metadata):
    by_sector=defaultdict(list)
    for s,v in scores.items():by_sector[metadata[s]["sector"]].append(v)
    centers={sector:sum(values)/len(values) for sector,values in by_sector.items()}
    return {s:v-centers[metadata[s]["sector"]] for s,v in scores.items()}


def trailing_return(rows, days, *, skip_recent=0):
    if days<=0 or skip_recent<0:
        raise ValueError("Invalid horizon")
    finish=len(rows)-skip_recent
    if finish-days-1<0:return None
    previous=rows[finish-days-1]["close"]
    final=rows[finish-1]["close"]
    return final/previous-1.0 if previous>0 else None


def volatility_from_prices(rows, *, days=30):
    if len(rows)<days+1:return None
    xs=[x["close"] for x in rows[-days-1:]]
    if any(x<=0 for x in xs):return None
    returns=[xs[i]/xs[i-1]-1 for i in range(1,len(xs))]
    center=sum(returns)/len(returns)
    return sqrt(252*sum((r-center)**2 for r in returns)/(len(returns)-1))


def inverse_vol_weight(scores, vol, *, epsilon=0.05):
    return {s:float(v)/max(epsilon,vol.get(s,epsilon)) for s,v in scores.items()}


def normalize_long_short(scores, *, gross=0.70):
    """Dollar-neutral continuous weights with symmetric long/short budgets."""
    positives={s:max(0,v) for s,v in scores.items()}
    negatives={s:max(0,-v) for s,v in scores.items()}
    p=sum(positives.values());n=sum(negatives.values())
    if p<1e-12 or n<1e-12:
        return {s:0.0 for s in scores}
    return {s:(0.5*gross*positives[s]/p-0.5*gross*negatives[s]/n) for s in scores}


def enforce_borrow_liquidity(weights, bars, *, min_adv=1_000_000, max_weight=0.035):
    revised={}
    for s,w in weights.items():
        bar=bars[s]
        if bar["halted"] or bar["stale"] or bar["adv_usd"]<min_adv:
            revised[s]=0.0
        elif w<0 and not bar["borrow_available"]:
            revised[s]=0.0
        else:
            revised[s]=max(-max_weight,min(max_weight,w))
    return revised


def neutralize_sector(weights, meta):
    """Subtract average sector weight; shrinks book but does not invent positions."""
    groups=defaultdict(list)
    for s in weights:groups[meta[s]["sector"]].append(s)
    out=dict(weights)
    for sector,syms in groups.items():
        off=sum(weights[s] for s in syms)/len(syms)
        for s in syms:out[s]-=off
    return out


def neutralize_beta(weights, betas, *, strength=1.0):
    """Soft beta projection into the beta-net-zero hyperplane.

    For a 48-name universe, a single projection is not enough after clipping
    and borrow restrictions. The caller should iterate, inspect and validate.
    """
    if not 0<=strength<=1:raise ValueError("Invalid projection strength")
    symbols=[s for s in weights if s in betas]
    if len(symbols)<2:return dict(weights)
    avg_b=sum(betas[s] for s in symbols)/len(symbols)
    centered={s:betas[s]-avg_b for s in symbols}
    denom=sum(v*v for v in centered.values())
    if denom<1e-12:return dict(weights)
    beta_load=sum(weights[s]*betas[s] for s in symbols)
    out=dict(weights)
    for s in symbols:out[s]-=strength*beta_load*centered[s]/denom
    return out


def no_trade_band(target, held, *, band=0.002):
    if band<0:raise ValueError("Negative no-trade band")
    return {s:(held.get(s,0) if abs(w-held.get(s,0))<band else w) for s,w in target.items()}


def exposure_report(weights, meta, betas=None):
    report=portfolio_exposures(weights,meta,betas)
    report["names_long"]=sum(w>1e-6 for w in weights.values())
    report["names_short"]=sum(w< -1e-6 for w in weights.values())
    return report


def moving_block_bootstrap(returns, *, block_size=10, draws=500, seed=0):
    """Bootstrap cumulative returns with blocks instead of IID shuffling.

    This preserves short-term autocorrelation approximately; it does not prove
    that future alpha exists. Read empirical confidence ranges cautiously.
    """
    if not returns or block_size<1 or block_size>len(returns) or draws<1:
        raise ValueError("Invalid bootstrap shape")
    rng=random.Random(seed)
    n=len(returns)
    result=[]
    for _ in range(draws):
        sample=[]
        while len(sample)<n:
            i=rng.randint(0,n-block_size)
            sample.extend(returns[i:i+block_size])
        wealth=1.0
        for r in sample[:n]:wealth*=(1+r)
        result.append(wealth-1)
    return result


def deflated_sharpe_warning(sharpe, strategy_variants):
    """Interpretability helper: not a statistical deflated-Sharpe estimator."""
    if strategy_variants<1:raise ValueError("At least one trial")
    return {
        "observed_sharpe":sharpe,
        "reported_trials":strategy_variants,
        "selection_bias_warning":strategy_variants>1,
        "message":"A selected best Sharpe is optimistic after multiple trials; use independent holdout.",
    }


def rebalance_cost_estimate(target, held, bars, *, fee_bps=1.0, impact_bps=12.0):
    """Rough ex-ante fractional-equity cost with ADV-relative impact."""
    result=0.0
    for s,w in target.items():
        change=abs(w-held.get(s,0.0))
        bar=bars[s]
        # Compare a hypothetical $1m book against current ADV; price not needed.
        participation=min(1.0,change*1_000_000/max(1.0,bar["adv_usd"]))
        result+=change*(fee_bps+bar["spread_bps"]/2+impact_bps*sqrt(participation))/10000
    return result
