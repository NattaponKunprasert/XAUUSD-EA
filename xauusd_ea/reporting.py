"""Reproducible reporting for the fixed M15 smoke configuration set."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .baseline import (
    fixed_m15_smoke_configs,
    load_broker_profile,
    load_mt5_csv,
    run_m15_baseline_smoke,
)


def build_m15_smoke_report(project_root: str | Path, max_rows: int = 5000) -> dict:
    root = Path(project_root).resolve()
    profile_path = root / "config" / "xm_micro_gold.json"
    data_path = root / "XAUUSD_M15.csv"
    broker = load_broker_profile(profile_path)
    frame = load_mt5_csv(data_path).iloc[:max_rows].copy()
    configs = fixed_m15_smoke_configs(broker)
    results = [run_m15_baseline_smoke(frame, broker, config) for config in configs]

    code_hasher = hashlib.sha256()
    for source in sorted((root / "xauusd_ea").glob("*.py")):
        code_hasher.update(source.name.encode())
        code_hasher.update(source.read_bytes())

    return {
        "label": "research-smoke",
        "evaluation": "earliest-M15-segment; no holdout; no ranking",
        "timeframe": "M15",
        "rows": len(frame),
        "data_start": frame.index[0].isoformat(),
        "data_end": frame.index[-1].isoformat(),
        "data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "broker_config_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        "code_sha256": code_hasher.hexdigest(),
        "candidate_count": len(configs),
        "random_seed": None,
        "cost_profile": {
            "spread_multipliers": list(broker.spread_stress_multipliers),
            "commission_round_turn_usd": broker.commission_per_lot_round_turn_usd,
            "fee_round_turn_usd": broker.fee_per_lot_round_turn_usd,
            "swap_long_points": broker.swap_long_points,
            "swap_short_points": broker.swap_short_points,
            "triple_swap_day": broker.triple_swap_day,
        },
        "runs": [
            {
                "config": config,
                "trade_count": result["trade_count"],
                "final_capital": result["final_capital"],
            }
            for config, result in zip(configs, results)
        ],
    }


def write_report(report: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run audited M15 smoke scenarios")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--max-rows", type=int, default=5000)
    parser.add_argument(
        "--output", type=Path, default=Path("outputs/m15_smoke_report.json")
    )
    args = parser.parse_args()
    report = build_m15_smoke_report(args.project_root, args.max_rows)
    output = write_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Smoke report written to: {output.resolve()}")


if __name__ == "__main__":
    main()
