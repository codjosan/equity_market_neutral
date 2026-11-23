"""Deterministic, reproducible adversarial execution/market overlays.

All adjustments are applied by the engine to its own day-bar copies; a
strategy never receives a scenario flag or tomorrow's bar/auction conditions.
"""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Scenario:
    name: str = "base"
    spread_multiplier: float = 1.0
    impact_multiplier: float = 1.0
    commission_multiplier: float = 1.0
    borrow_multiplier: float = 1.0
    adv_multiplier: float = 1.0
    max_participation: float = 0.05
    outage_sector: str = ""
    outage_symbols: tuple = ()
    outage_start: int = 0
    outage_end: int = 0
    recall_sector: str = ""
    recall_start: int = 0
    recall_end: int = 0
    shock_sector: str = ""
    shock_start: int = -1
    shock_return: float = 0.0
    rejection_modulus: int = 0
    auction_impact_penalty_bps: float = 0.0

    def __post_init__(self):
        for v in (self.spread_multiplier, self.impact_multiplier, self.commission_multiplier,
                  self.borrow_multiplier, self.adv_multiplier, self.max_participation):
            if not isfinite(v) or v < 0:
                raise ValueError("Scenario multipliers/participation must be nonnegative finite")
        if self.max_participation > 1:
            raise ValueError("Participation must not exceed 100% of ADV")
        if not (-0.99 < self.shock_return < 3.0):
            raise ValueError("Shock return out of bounds")
        if self.rejection_modulus < 0:
            raise ValueError("Invalid rejection modulus")

    def apply(self, source, symbol, sector, index):
        bar = dict(source)
        bar["spread_bps"] *= self.spread_multiplier
        bar["adv_usd"] *= self.adv_multiplier
        bar["borrow_rate_annual"] *= self.borrow_multiplier
        if self.outage_start <= index <= self.outage_end and (
            (self.outage_sector and sector == self.outage_sector)
            or symbol in self.outage_symbols
        ):
            bar["halted"] = True
        if (self.recall_sector and sector == self.recall_sector
                and self.recall_start <= index <= self.recall_end):
            bar["borrow_available"] = False
        if self.shock_sector and sector == self.shock_sector and index >= self.shock_start:
            multiple = 1.0 + self.shock_return
            for price_field in ("open", "high", "low", "close"):
                bar[price_field] *= multiple
        return bar


# Standard suite of 12 deterministic execution and market stress scenarios.
def stress_cases():
    return (
        Scenario("base"),
        Scenario("double_all_costs", spread_multiplier=2, impact_multiplier=2,
                 commission_multiplier=2, borrow_multiplier=2),
        Scenario("quadruple_impact", impact_multiplier=4),
        Scenario("depth_collapse", adv_multiplier=0.18, max_participation=0.015),
        Scenario("wide_spreads", spread_multiplier=5),
        Scenario("borrow_squeeze", borrow_multiplier=5, recall_sector="TECH",
                 recall_start=271, recall_end=299),
        Scenario("sector_outage", outage_sector="FINANCIALS", outage_start=280, outage_end=293),
        Scenario("symbol_outage", outage_symbols=("EQ01", "EQ02", "EQ17", "EQ41"),
                 outage_start=300, outage_end=327),
        Scenario("one_day_auction_shock", shock_sector="TECH", shock_start=304,
                 shock_return=-0.18),
        Scenario("industrial_gap_shock", shock_sector="INDUSTRIALS", shock_start=316,
                 shock_return=-0.13),
        Scenario("random_rejections", rejection_modulus=13),
        Scenario("auction_dislocation", auction_impact_penalty_bps=18,
                 spread_multiplier=1.5, max_participation=0.025),
    )


def scenario_by_name(name):
    for scenario in stress_cases():
        if scenario.name == name:
            return scenario
    raise ValueError("Unknown scenario: " + name)
