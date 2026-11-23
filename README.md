# Equity Market-Neutral Quantitative Research Study

An offline, zero-dependency Python framework for developing, backtesting, diagnosing, and stress-testing cross-sectional daily long/short equity market-neutral strategies.

## Project Overview

The study simulates a 48-equity, 6-sector universe across 504 synthetic trading days (`2024-01-02` to `2025-12-05`), divided chronologically into:
- **Train:** 252 trading days
- **Validation:** 84 trading days
- **Test:** 168 trading days

### Execution & Risk Mechanics
- **Point-in-Time Timing:** Strategies observe daily OHLCV, spread, ADV, stock-borrow availability, and market/sector factor returns at day $t$'s close via `on_day(context)` and output target portfolio weights. Orders execute at day $t+1$'s open.
- **Execution Friction:** Fills are subject to quoted bid-ask spreads, ADV-relative market impact, commissions, minimum order thresholds, participation caps, and unexecutable halted or stale sessions.
- **Short Borrow Accounting:** Short positions require locate availability at entry, accrue daily borrow fees based on `borrow_rate_annual`, and are subject to forced buy-ins upon borrow recalls.
- **Portfolio Constraints:** Strategies are evaluated against exposure limits ($\le 1.50\times$ gross exposure, $\le 0.03\times$ net exposure, $\le 0.05\times$ single-name weight, $\le 0.08\times$ sector net exposure), PnL reconciliation checks, and 12 deterministic market and execution stress scenarios.

## Repository Structure

```text
.
├── data/
│   ├── DATA_DICTIONARY.md        # Schema and field definitions
│   ├── daily_bars.csv            # 24,192 daily asset price, volume, spread, and borrow records
│   ├── market_factors.csv        # 504 daily market and sector return records
│   ├── universe.csv              # 48 symbols mapped to sectors and market capitalizations
│   └── manifest.json             # Dataset metadata and partition counts
├── outputs/                      # Reference baseline outputs and diagnostics
├── research/                     # Standalone exploratory research scripts
├── scripts/
│   ├── audit_data.py             # Dataset integrity, chronology, and OHLC validation
│   ├── factor_diagnostics.py     # Post-trade factor regression and PnL reconciliation
│   ├── run_baseline.py           # Benchmark strategy execution across all splits
│   ├── run_stress.py             # 12-scenario execution and market stress suite
│   └── run_unit_tests.py         # Full unittest suite runner
├── src/marketneutral_equity/
│   ├── candidate/                # Optional modular strategy components
│   ├── data.py                   # Point-in-time CSV dataset loader
│   ├── diagnostics.py            # Factor loadings and trade reconciliation utilities
│   ├── engine.py                 # Daily cash/share simulator and order execution engine
│   ├── metrics.py                # Return, drawdown, Sharpe, exposure, and gate metrics
│   ├── research_tools.py         # Cross-sectional scoring, neutralization, and bootstrap tools
│   ├── risk.py                   # Exposure calculations and pre-trade/post-fill risk checks
│   ├── runner.py                 # CLI runner for baseline and candidate strategies
│   ├── scenarios.py              # Definitions for the 12 deterministic stress cases
│   ├── strategy.py               # Candidate strategy implementation (`CandidateStrategy`)
│   └── strategy_baseline.py      # Reference 5-day reversal benchmark (`SimpleReversalBaseline`)
├── tests/                        # Unit test suite covering engine, dataset, tools, and scenarios
├── pyproject.toml                # Package metadata (Python >= 3.10, standard library only)
└── requirements.txt              # Dependency declaration (none required)
```

## Setup

Requires **Python 3.10 or newer** with no external packages. From the project root, scripts automatically resolve `src/` on `PYTHONPATH`, or you can install the package in editable mode:

```bash
pip install --no-build-isolation --no-deps -e .
```

## Script Commands

### 1. Audit Dataset Integrity
Verify dataset completeness, chronological ordering, OHLC bounds, liquidity fields, and split partitions:
```bash
python scripts/audit_data.py
```

### 2. Run the Baseline Benchmark
Execute the reference five-day reversal strategy across `train`, `validation`, and `test` partitions:
```bash
python scripts/run_baseline.py
```

### 3. Run the Candidate Strategy
Implement your strategy in `src/marketneutral_equity/strategy.py` (`CandidateStrategy.on_day`) and run it on a target split:
```bash
python -m marketneutral_equity.runner --strategy candidate --split train --output-dir outputs/candidate_train
python -m marketneutral_equity.runner --strategy candidate --split validation --output-dir outputs/candidate_validation
python -m marketneutral_equity.runner --strategy candidate --split test --output-dir outputs/candidate_test
```

### 4. Run Factor & PnL Diagnostics
Compute realized market/sector factor loadings, turnover, cost attribution, and execution reconciliation:
```bash
python scripts/factor_diagnostics.py --strategy candidate --split train --out outputs/candidate_factor_diagnostics.json
```

### 5. Run the 12-Scenario Stress Matrix
Evaluate strategy resilience across cost multipliers, depth collapse, wide spreads, borrow squeezes, sector/symbol outages, gap shocks, and auction dislocations:
```bash
python scripts/run_stress.py --strategy candidate --split validation --out outputs/candidate_stress_matrix.json
```

## Running Tests

Execute the entire unit test suite (and any custom `tests/test_candidate*.py` test modules) using the standard library `unittest` runner:

```bash
python scripts/run_unit_tests.py
```

Alternatively, run `unittest` directly from the repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
