"""Candidate strategy module.

Implement your strategy in CandidateStrategy.on_day(context) returning a
SYMBOL -> TARGET PORTFOLIO WEIGHT mapping.

Timing:
    t close: on_day sees OHLCV / spread / borrow / ADV through t and factor
             rows through t. It submits target weights for next session open.
    t+1 open: the engine converts target weights into share orders and fills
              under next-session auction, borrow, and liquidity state, or rejects.
    t+1 close: holdings are marked to market and borrow fees are accrued.

No future bars, tomorrow's auction, hidden regime labels, true betas, or
reporting split labels are exposed by Context. Do not tune parameters on the
validation or test partitions.

Context fields:
    date, bars, history, factor_history, universe, positions, equity,
    peak_equity, drawdown, cash, pending_order_count.

Target exposure limits: <=1.50 gross, <=0.03 net, <=0.05 single name, <=0.08 sector net.
"""


class CandidateStrategy:
    def __init__(self):
        self.parameters = {}

    def on_day(self, context):
        return {}
