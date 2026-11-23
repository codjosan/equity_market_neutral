"""Daily equity backtest with next-open execution and cash/share accounting.

Timeline (day t):
    1. Existing positions are carried overnight at the t open.
    2. Target-share orders submitted after the t-1 close attempt to fill at t open.
    3. Portfolio is marked at t close; cash borrow is charged for the day.
    4. Strategy sees data through t close and submits orders for t+1 open.

No strategy can query future rows, reporting split labels, hidden factor betas,
or execution-time data for t+1. No overnight-to-close price PnL is omitted.
"""
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import csv
import json
import math
import zlib

from .data import load_dataset
from .risk import constraint_violations, portfolio_exposures
from .scenarios import Scenario


@dataclass(frozen=True)
class EngineConfig:
    starting_equity: float = 1_000_000.0
    max_gross: float = 1.50
    max_abs_net: float = 0.03
    max_abs_position: float = 0.05
    max_abs_sector_net: float = 0.08
    commission_bps: float = 1.0
    impact_coefficient_bps: float = 12.0
    lot_size_shares: float = 0.001
    max_drawdown_warning: float = 0.10
    min_order_notional: float = 10.0

    def __post_init__(self):
        for name, value in self.__dict__.items():
            if not math.isfinite(value) or value < 0:
                raise ValueError("Config must be finite and nonnegative: " + name)
        if self.starting_equity <= 0 or self.max_gross <= 0 or self.max_abs_position <= 0:
            raise ValueError("Equity and leverage limits must be positive")


@dataclass(frozen=True)
class Context:
    date: str
    bars: dict
    history: dict
    factor_history: list
    universe: dict
    positions: dict
    equity: float
    peak_equity: float
    drawdown: float
    cash: float
    pending_order_count: int


class Engine:
    def __init__(self, data_dir, config=None, scenario=None):
        self.dates, self.by_date, self.factor_by_date, self.history, self.meta = load_dataset(data_dir)
        self.config = config or EngineConfig()
        self.scenario = scenario or Scenario()
        self.symbols = sorted(self.meta)
        if set(self.factor_by_date) != set(self.dates):
            raise ValueError("Factor dates do not match prices")
        if any(set(day) != set(self.meta) for day in self.by_date.values()):
            raise ValueError("Missing or extra daily asset observations")

    @staticmethod
    def weights(shares, marks, equity):
        return {s: shares[s]*marks[s]/max(1.0,equity) for s in shares}

    def _validate_request(self, requested):
        if not isinstance(requested, dict):
            return None, "invalid_target_format"
        if set(requested).difference(self.meta):
            return None, "unknown_symbol"
        try:
            values = {s: float(requested.get(s, 0.0)) for s in self.symbols}
        except (TypeError, ValueError, OverflowError):
            return None, "invalid_target_format"
        issues = constraint_violations(values, self.meta, self.config)
        if issues:
            return None, "invalid_target_"+issues[0]
        return values, ""

    def _execute(self, date, index, bars, pending, shares, cash, previous_close, events, trades):
        cfg, sc = self.config, self.scenario
        pre_shares = dict(shares)
        equity_at_open = cash + sum(shares[s]*bars[s]["open"] for s in shares)
        if equity_at_open <= 0:
            events["insolvent_equity"] += 1
            return cash, 0.0, 0.0, 0.0, 0.0
        forced, proposed = {}, {}
        for s in self.symbols:
            row = bars[s]
            old = shares[s]
            desired_delta = pending.get(s, 0.0)
            if old < -1e-10 and not row["borrow_available"]:
                # A borrow recall triggers an exchange-style mandatory buy-in.
                # If the market is halted/stale, the recall remains unresolved.
                forced[s] = -old
                desired_delta = -old
                events["borrow_recall"] += 1
            if abs(desired_delta) < 1e-12:
                continue
            if row["halted"] or row["stale"]:
                events["blocked_halt_stale"] += 1
                if s in forced:
                    events["unresolved_borrow_recall"] += 1
                continue
            if (sc.rejection_modulus and
                zlib.crc32((date+"|"+s).encode()) % sc.rejection_modulus == 0):
                events["auction_rejection"] += 1
                continue
            # Do not open or add to a short without borrow. A recall can force a buy.
            if desired_delta < 0 and old+desired_delta < -1e-10 and not row["borrow_available"]:
                desired_delta = max(0.0, -old) if old < 0 else 0.0
                events["short_locate_block"] += 1
            if abs(desired_delta)*row["open"] < cfg.min_order_notional and s not in forced:
                events["min_order_block"] += 1
                continue
            if s in forced:
                # Forced buy-ins have priority over participation caps, but pay
                # an additional execution penalty to reflect urgency.
                proposed[s] = desired_delta
            else:
                cap = sc.max_participation * row["adv_usd"]
                maximum_shares = cap/max(1e-12, row["open"])
                clipped = math.copysign(min(abs(desired_delta),maximum_shares),desired_delta)
                if abs(clipped-desired_delta)>1e-9:
                    events["partial_fill"] += 1
                lot = cfg.lot_size_shares
                proposed[s] = math.trunc(clipped/lot)*lot if lot else clipped

        forced_deltas = {s:proposed[s] for s in forced if s in proposed}
        discretionary = {s:q for s,q in proposed.items() if s not in forced_deltas}

        def weights_at_scale(scale):
            simulated = dict(pre_shares)
            for s,q in forced_deltas.items():
                simulated[s]+=q
            for s,q in discretionary.items():
                simulated[s]+=q*scale
            return self.weights(simulated,{s:bars[s]["open"] for s in simulated},equity_at_open)

        # If an auction rejects one leg, the entire discretionary basket must be
        # rebalanced at portfolio level, not accepted as an accidental naked bet.
        # Forced recalls are non-discretionary and may temporarily violate limits.
        base_issues = constraint_violations(weights_at_scale(0), self.meta, cfg, tolerance=1e-6)
        full_issues = constraint_violations(weights_at_scale(1), self.meta, cfg, tolerance=1e-6)
        scale = 1.0
        if full_issues:
            if base_issues:
                scale = 0.0
                events["infeasible_forced_or_gap"] += 1
            else:
                lo, hi = 0.0, 1.0
                for _ in range(36):
                    mid=(lo+hi)/2
                    if constraint_violations(weights_at_scale(mid),self.meta,cfg,tolerance=1e-6):
                        hi=mid
                    else:
                        lo=mid
                scale=lo
            events["risk_scale_or_cancel"] += 1

        commission_total = spread_total = impact_total = turnover_total = 0.0
        for s in self.symbols:
            quantity = forced_deltas.get(s,0.0) + scale*discretionary.get(s,0.0)
            if abs(quantity) < 1e-10:
                continue
            bar=bars[s]
            mid=bar["open"]
            notional=abs(quantity)*mid
            participation=min(1.0,notional/max(1.0,bar["adv_usd"]))
            half_spread_bps=bar["spread_bps"]/2
            impact_bps=cfg.impact_coefficient_bps*sc.impact_multiplier*math.sqrt(participation)
            if s in forced_deltas:
                impact_bps+=25.0  # forced-market-order penalty
            impact_bps+=sc.auction_impact_penalty_bps
            commission=notional*cfg.commission_bps*sc.commission_multiplier/10000
            spread=notional*half_spread_bps/10000
            impact=notional*impact_bps/10000
            costs=commission+spread+impact
            side=1 if quantity>0 else -1
            fill_price=mid*(1+side*(half_spread_bps+impact_bps)/10000)
            cash-=quantity*fill_price+commission
            shares[s]+=quantity
            commission_total+=commission
            spread_total+=spread
            impact_total+=impact
            turnover_total+=notional
            trades.append({
                "date":date,"symbol":s,"side":"buy" if side>0 else "sell",
                "forced_buyin":int(s in forced_deltas),"shares":round(quantity,9),
                "mid_open":round(mid,6),"fill_price":round(fill_price,6),
                "notional_usd":round(notional,2),"commission_usd":round(commission,4),
                "spread_cost_usd":round(spread,4),"impact_cost_usd":round(impact,4),
                "participation_adv":round(participation,8),"risk_scale":round(scale,8)
            })
        if constraint_violations(self.weights(shares,{s:bars[s]["open"] for s in shares},
                                            cash+sum(shares[s]*bars[s]["open"] for s in shares)),
                                 self.meta,cfg,tolerance=1e-6):
            events["open_risk_exception"] += 1
        return cash,commission_total,spread_total,impact_total,turnover_total

    def run(self, strategy, *, split="all", output_dir=None):
        if split not in ("all","train","validation","test"):
            raise ValueError("split must be train, validation, test or all")
        cfg=self.config
        shares={s:0.0 for s in self.symbols}
        cash=cfg.starting_equity
        equity=cfg.starting_equity
        peak=equity
        previous_close={}
        visible_history={s:[] for s in self.symbols}
        visible_factors=[]
        pending={}
        events=defaultdict(int)
        trades=[]
        daily=[]
        risk_events=[]
        seen_active = False
        for index,date in enumerate(self.dates):
            current_partition=self.factor_by_date[date]["split"]
            if split!="all" and seen_active and current_partition!=split:
                break
            if current_partition==split:
                seen_active=True
            base=self.by_date[date]
            bars={s:self.scenario.apply(base[s],s,self.meta[s]["sector"],index)
                  for s in self.symbols}
            current_split=self.factor_by_date[date]["split"]
            old_shares=dict(shares)
            starting_equity=equity
            overnight_pnl=sum(old_shares[s]*(bars[s]["open"]-previous_close[s])
                              for s in self.symbols) if previous_close else 0.0
            commission=spread_cost=impact_cost=turnover=0.0
            if split=="all" or current_split==split:
                cash,commission,spread_cost,impact_cost,turnover = self._execute(
                    date,index,bars,pending,shares,cash,previous_close,events,trades)
            pending={}
            intraday_pnl=sum(shares[s]*(bars[s]["close"]-bars[s]["open"])
                             for s in self.symbols)
            borrow_cost=sum(max(0.0,-shares[s])*bars[s]["close"]*
                            bars[s]["borrow_rate_annual"]/252 for s in self.symbols)
            cash-=borrow_cost
            equity=cash+sum(shares[s]*bars[s]["close"] for s in self.symbols)
            if not math.isfinite(equity) or equity <= 0:
                events["insolvent_equity"]+=1
                raise ArithmeticError("Non-finite or insolvent equity")
            net_change=equity-starting_equity
            recon=overnight_pnl+intraday_pnl-commission-spread_cost-impact_cost-borrow_cost
            if abs(recon-net_change)>max(0.01,1e-8*equity):
                events["pnl_reconciliation_failed"]+=1
            peak=max(peak,equity)
            drawdown=1.0-equity/peak
            if drawdown>cfg.max_drawdown_warning:
                events["drawdown_warning"]+=1
            close_weights=self.weights(shares,{s:bars[s]["close"] for s in self.symbols},equity)
            exposures=portfolio_exposures(close_weights,self.meta)
            issues=constraint_violations(close_weights,self.meta,cfg,tolerance=1e-6)
            if issues:
                events["close_risk_exception"]+=1
                risk_events.append({"date":date,"split":current_split,"issues":issues,
                                    "gross":exposures["gross"],"net":exposures["net"]})
            daily.append({
                "date":date,"split":current_split,"equity":equity,
                "start_equity":starting_equity,"net_pnl":net_change,
                "overnight_price_pnl":overnight_pnl,"intraday_price_pnl":intraday_pnl,
                "borrow_cost":borrow_cost,"commission":commission,
                "spread_cost":spread_cost,"impact_cost":impact_cost,
                "trading_cost":commission+spread_cost+impact_cost,
                "turnover_usd":turnover,"gross_exposure":exposures["gross"],
                "net_exposure":exposures["net"],"max_name_weight":exposures["max_name"],
                "max_sector_net":max((abs(x) for x in exposures["sector_net"].values()),default=0),
                "drawdown":drawdown,"pnl_reconciliation_error":net_change-recon,
                "risk_issue_count":len(issues),
            })
            previous_close={s:bars[s]["close"] for s in self.symbols}
            # Strategy sees only data available by this date's close; no label.
            for s in self.symbols:
                visible_history[s].append({k:v for k,v in bars[s].items() if k!="split"})
            visible_factors.append({k:v for k,v in self.factor_by_date[date].items() if k!="split"})
            context=Context(date=date,
                bars={s:dict(visible_history[s][-1]) for s in self.symbols},
                history={s:[dict(x) for x in visible_history[s]] for s in self.symbols},
                factor_history=[dict(x) for x in visible_factors],
                universe={s:dict(x) for s,x in self.meta.items()},
                positions=dict(close_weights),equity=equity,peak_equity=peak,
                drawdown=drawdown,cash=cash,pending_order_count=0)
            try:
                requested=strategy.on_day(context)
            except Exception as exc:
                events["strategy_exception"]+=1
                if len(risk_events)<300:
                    risk_events.append({"date":date,"type":"strategy_exception","detail":repr(exc)})
                requested=None
            target,reason=self._validate_request(requested)
            if reason:
                events[reason]+=1
                target=None
            if target is not None and (split=="all" or current_split==split):
                for s in self.symbols:
                    desired_shares=target[s]*equity/max(1e-12,bars[s]["close"])
                    delta=desired_shares-shares[s]
                    if abs(delta)*bars[s]["close"] >= cfg.min_order_notional:
                        pending[s]=delta
        if split != "all":
            # Only report the selected chronological partition, after complete
            # market-history warm-up. No out-of-split fills are permitted.
            daily=[row for row in daily if row["split"]==split]
            trades=[row for row in trades if self.factor_by_date[row["date"]]["split"]==split]
            risk_events=[row for row in risk_events if row.get("split",split)==split]
        result={"daily":daily,"trades":trades,"events":dict(events),
                "risk_events":risk_events,"scenario":self.scenario.name,
                "split":split,"starting_equity":cfg.starting_equity,
                "final_equity":daily[-1]["equity"] if daily else cfg.starting_equity}
        if output_dir:
            self.export(result,output_dir)
        return result

    @staticmethod
    def export(result,folder):
        path=Path(folder);path.mkdir(parents=True,exist_ok=True)
        for filename,rows in (("daily_equity.csv",result["daily"]),
                              ("trades.csv",result["trades"])):
            fields=sorted({key for row in rows for key in row}) or ["date"]
            with (path/filename).open("w",newline="",encoding="utf-8") as f:
                writer=csv.DictWriter(f,fieldnames=fields)
                writer.writeheader();writer.writerows(rows)
        (path/"events.json").write_text(json.dumps(result["events"],indent=2),encoding="utf-8")
        (path/"risk_events.json").write_text(json.dumps(result["risk_events"],indent=2),encoding="utf-8")
