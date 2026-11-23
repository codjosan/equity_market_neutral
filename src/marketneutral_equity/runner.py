"""Standalone reproducible runner for benchmark or candidate by split."""
from argparse import ArgumentParser
from pathlib import Path
import json
from .engine import Engine
from .metrics import summarize, objective_failures
from .strategy import CandidateStrategy
from .strategy_baseline import SimpleReversalBaseline
from .scenarios import scenario_by_name


def run(strategy="candidate", split="train", scenario="base", data="data", out=None):
    if strategy not in ("candidate", "baseline"):
        raise ValueError("Unknown strategy")
    strat = CandidateStrategy() if strategy == "candidate" else SimpleReversalBaseline()
    engine = Engine(data, scenario=scenario_by_name(scenario))
    result = engine.run(strat, split=split, output_dir=out)
    summary = summarize(result)
    summary["objective_failures"] = objective_failures(
        summary, require_profit=split in ("validation", "test")
    )
    if out:
        out_path = Path(out)
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    ap = ArgumentParser()
    ap.add_argument("--strategy", choices=("baseline", "candidate"), default="candidate")
    ap.add_argument("--split", choices=("train", "validation", "test", "all"), default="train")
    ap.add_argument("--scenario", default="base")
    ap.add_argument("--data", default="data")
    ap.add_argument("--output-dir", default="outputs/candidate")
    args = ap.parse_args()
    print(json.dumps(run(args.strategy, args.split, args.scenario, args.data, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
