# Synthetic Equity Data Dictionary

**All records are simulated and do not originate from any real issuer or securities market.** The underlying return-generating process is omitted to preserve blind signal research. The supplied CSV files and manifest are sufficient to run every offline test and backtest.

| File | Rows | Columns |
|---|---:|---|
| `daily_bars.csv` | 24,192 | `date`, `symbol`, `open`, `high`, `low`, `close`, `volume`, `adv_usd`, `spread_bps`, `halted`, `stale`, `borrow_available`, `borrow_rate_annual`, `split` |
| `market_factors.csv` | 504 | `date`, `market_return`, `market_vol_proxy`, sector return columns, `split` |
| `universe.csv` | 48 | `symbol`, `sector`, `market_cap_usd` |

The six sectors are `TECH`, `FINANCIALS`, `HEALTHCARE`, `INDUSTRIALS`, `CONSUMER`, and `ENERGY`, with eight names per sector. All dates are ISO dates representing synthetic business days without actual exchange holidays.

`spread_bps` is the full quoted spread, and normal liquidity impact depends on auction notional relative to `adv_usd`. `borrow_rate_annual` is a decimal annual interest rate (e.g., `0.025` equals 2.5% per year). `borrow_available` indicates locate availability on that day and does not guarantee continued borrow availability on subsequent days. `halted` or `stale` renders that day's open unexecutable in the simulator.

`market_return` and sector returns refer to the stated trading date's factor performance and are available after the close of that date. `split` exists only for evaluation reporting and is excluded from the strategy `on_day` context.

The dataset spans 504 trading days: 252 `train` days, 84 `validation` days, and 168 `test` days (seed `20261122`). The point-in-time loader enforces matching factor dates and a complete 48-name universe. Run `scripts/audit_data.py` to verify completeness, chronology, OHLC bounds, and constraints prior to backtesting.
