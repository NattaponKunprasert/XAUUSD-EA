import ast
import copy
from datetime import datetime
import glob
import hashlib
import itertools
import json
import math
import os
import pickle
from pathlib import Path
import random
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pytest

from xauusd_ea.accounting import (
    book_crossed_rollover_swaps,
    close_position,
    mark_to_market_equity,
)
from xauusd_ea.baseline import (
    assert_runtime_broker_spec_matches_profile,
    crossed_rollover_swap_cash,
    load_broker_profile,
    load_mt5_csv,
    merge_runtime_broker_overrides,
    require_runtime_broker_spec,
)
from xauusd_ea.exits import (
    fibonacci_extension_target,
    max_holding_exit_due,
    next_trailing_stop,
)
from xauusd_ea.execution import (
    apply_execution_price,
    commission_per_side,
    spread_price,
    to_price_units,
)
from xauusd_ea.filters import passes_entry_filters
from xauusd_ea.indicators import (
    average_true_range,
    bollinger_bands,
    exponential_moving_average,
    macd,
    relative_strength_index,
    stochastic_oscillator,
)
from xauusd_ea.sizing import calculate_position_size
from xauusd_ea.validation import (
    SampleHoldoutSplit,
    UnsafeEvaluationError,
    WalkForwardWindow,
    assert_exact_forward_config_identity,
    assert_expected_research_config_fingerprint,
    plan_walk_forward_windows,
    research_config_fingerprint,
    split_sample_holdout,
)

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "EA_XAUUSD_29102025_Master_FIXED_V3_9_HOLDOUT_SAFE_EXACT_FORWARD (1).ipynb"


def _make_timeframe_df(periods: int = 10) -> pd.DataFrame:
    index = pd.date_range("2025-01-01 00:00", periods=periods, freq="15min")
    return pd.DataFrame(
        {
            "open": range(periods),
            "high": range(periods),
            "low": range(periods),
            "close": range(periods),
            "volume": [1.0] * periods,
        },
        index=index,
    )


def _notebook_code_source() -> str:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook.get("cells", [])
        if cell.get("cell_type") == "code"
    )


def _notebook_cell_source(index: int) -> str:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "".join(notebook["cells"][index].get("source", []))


def _active_notebook_run_backtest():
    """Load the active engine definition without executing notebook orchestration."""
    source = _notebook_cell_source(18)
    tree = ast.parse(source)
    required_assignments = {"REQUIRED", "ALIASES", "DEFAULTS"}
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in required_assignments
            for target in node.targets
        ):
            nodes.append(node)
    sizing_tree = ast.parse(_notebook_cell_source(7))
    nodes.insert(
        0,
        next(
            node
            for node in sizing_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "calculate_position_size"
        ),
    )

    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    runtime_spec = assert_runtime_broker_spec_matches_profile(
        {
            **broker.to_runtime_spec(),
            "lot_precision": 2,
            "spread_application": "full",
            "cost_value_mode": "points",
            "spread_points": broker.spread_baseline_price / broker.point,
            "commission_per_lot_round_turn": 0.0,
            "fee_per_lot_round_turn": 0.0,
            "swap_per_lot": broker.swap_long_points * broker.point,
            "swap_long_per_lot": broker.swap_long_points * broker.point,
            "swap_short_per_lot": broker.swap_short_points * broker.point,
        },
        broker,
    )
    namespace = {
        "Any": Any,
        "Dict": Dict,
        "Iterable": Iterable,
        "List": List,
        "Optional": Optional,
        "Sequence": Sequence,
        "Tuple": Tuple,
        "datetime": datetime,
        "glob": glob,
        "hashlib": hashlib,
        "itertools": itertools,
        "json": json,
        "math": math,
        "os": os,
        "pickle": pickle,
        "random": random,
        "time": time,
        "copy": copy,
        "np": np,
        "pd": pd,
        "INITIAL_CAPITAL": 1000.0,
        "XAUUSD_SPEC": runtime_spec,
        "EXECUTION_MODE": "next_bar_open",
        "DEBUG_SIGNAL_COUNTS": False,
        "SAME_BAR_EXIT_POLICY": "SL_FIRST",
        "SKIP_RISK_LOT_BELOW_MIN": True,
        "crossed_rollover_swap_cash": crossed_rollover_swap_cash,
        "merge_runtime_broker_overrides": merge_runtime_broker_overrides,
        "require_runtime_broker_spec": require_runtime_broker_spec,
        "_calculate_fib_target_safe": fibonacci_extension_target,
        "_max_holding_exit_due_safe": max_holding_exit_due,
        "_next_trailing_stop_safe": next_trailing_stop,
        "_apply_execution_price_safe": apply_execution_price,
        "_commission_per_side_safe": commission_per_side,
        "_spread_price_safe": spread_price,
        "_to_price_units_safe": to_price_units,
        "_passes_entry_filters_safe": passes_entry_filters,
        "_calculate_position_size_safe": calculate_position_size,
        "_mark_to_market_equity_safe": mark_to_market_equity,
        "_book_crossed_rollover_swaps_safe": book_crossed_rollover_swaps,
        "_close_position_safe": close_position,
        "_atr": average_true_range,
        "_bollinger": bollinger_bands,
        "_ema": exponential_moving_average,
        "_macd": macd,
        "_rsi": relative_strength_index,
        "_stochastic": stochastic_oscillator,
        "entry_filters": {},
        "_valid_stop_target": lambda *args, **kwargs: True,
        "_intrabar_stop_target": lambda *args, **kwargs: (None, None),
    }
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, "<active-notebook-functions>", "exec"), namespace)
    return namespace["run_backtest"]


def test_split_sample_holdout_creates_non_overlapping_chronological_ranges():
    df = _make_timeframe_df(periods=10)

    split = split_sample_holdout(df, timeframe="M15", sample_ratio=0.70)

    assert isinstance(split, SampleHoldoutSplit)
    assert split.timeframe == "M15"
    assert split.split_index == 7
    assert len(split.sample) == 7
    assert len(split.holdout) == 3
    assert split.sample.index.equals(df.index[:7])
    assert split.holdout.index.equals(df.index[7:])
    assert split.sample_end < split.holdout_start


def test_active_notebook_routes_holdout_split_through_validation_helper():
    source = _notebook_code_source()

    assert "from xauusd_ea.validation import (" in source
    assert "split_sample_holdout(" in source
    assert "np.clip(sample_ratio" not in source
    assert "raw_df.iloc[0:0].copy()" not in source


def test_active_notebook_walk_forward_does_not_fallback_to_full_sample():
    source = _notebook_code_source()

    assert "plan_walk_forward_windows(" in source
    assert "timeframe=tf_name" in source
    assert "UnsafeEvaluationError" in source
    assert "FALLBACK_FULL_SAMPLE" not in source
    assert "falling back to full-sample evaluation" not in source


def test_active_notebook_records_exact_forward_config_fingerprint():
    source = _notebook_code_source()

    assert "assert_expected_research_config_fingerprint(" in source
    assert "sample_cfg = copy.deepcopy(cfg)" in source
    assert "assert_exact_forward_config_identity(sample_cfg, cfg)" in source
    assert "assert_exact_forward_config_identity(cfg, cfg)" not in source
    assert "sample_config_fingerprint" in source
    assert "Sample Config Fingerprint" in source
    assert "Research Config Fingerprint" in source


def test_active_notebook_has_one_production_definition_per_core_behavior():
    source = _notebook_code_source()

    assert source.count("def run_backtest(") == 1
    assert source.count("def compute_strategy_metrics(") == 1
    assert source.count("def clean_strategies(") == 1
    assert "def legacy_run_backtest(" in source
    assert "def legacy_compute_strategy_metrics(" in source
    assert "def legacy_clean_strategies(" in source


def test_active_notebook_isolates_legacy_fibonacci_target_and_uses_canonical_helper():
    source = _notebook_code_source()

    assert "if m in fib_levels or True" not in source
    assert "def calculate_fib_target(" not in source
    assert "def legacy_calculate_fib_target(" in source
    assert (
        "from xauusd_ea.exits import fibonacci_extension_target as "
        "_calculate_fib_target_safe" in source
    )
    assert 'config["exit"].get("fib_levels", [1.618])' in source
    assert "config[\"params\"].get(\"Fibonacci\", {})" not in source


def test_active_notebook_routes_trailing_stop_through_canonical_helper():
    source = _notebook_cell_source(18)

    assert "next_trailing_stop as _next_trailing_stop_safe" in source
    assert "new_sl = _next_trailing_stop_safe(" in source
    assert "current_atr=current_atr" in source
    assert "dist = current_atr * mult" not in source
    assert "steps = math.floor(max(0.0, favourable) / min_step)" not in source


def test_active_notebook_routes_max_holding_exit_through_canonical_helper():
    source = _notebook_code_source()
    active_source = _notebook_cell_source(18)

    assert "def check_max_holding(" not in source
    assert "def legacy_check_max_holding(" in source
    assert "max_holding_exit_due as _max_holding_exit_due_safe" in active_source
    assert "_max_holding_exit_due_safe(" in active_source
    assert "bars_held >= max_hold" not in active_source


def test_active_notebook_uses_canonical_candidate_indicator_math():
    source = _notebook_code_source()

    assert (
        "from xauusd_ea.indicators import average_true_range as _atr, "
        "bollinger_bands as _bollinger, exponential_moving_average as _ema, "
        "macd as _macd, relative_strength_index as _rsi, "
        "stochastic_oscillator as _stochastic" in source
    )
    assert "def _atr(" not in source
    assert "def _ema(" not in source
    assert "def _macd(" not in source
    assert "def _bollinger(" not in source
    assert "def _rsi(" not in source
    assert "def _stochastic(" not in source
    assert "_rsi(close, r_period)" in source
    assert "_macd(close, mf, ms, msg)" in source
    assert "_bollinger(close, b_period, b_mult)" in source
    assert "_atr(high, low, close, atr_period)" in source
    assert "_stochastic(high, low, close, kk, dd, sm)" in source


def test_active_notebook_routes_entry_composition_through_canonical_helper():
    source = _notebook_code_source()

    assert (
        "from xauusd_ea.entries import (\n"
        "    compose_entry_signals as _compose_entry_signals_safe,"
    ) in source
    assert "resolve_entry_pair as _resolve_entry_pair_safe" in source
    assert "return _compose_entry_signals_safe(" in source
    assert "return _resolve_entry_pair_safe(" in source
    assert "mat = pd.concat(signals, axis=1)" not in source
    assert "matrix = pd.concat(signals, axis=1)" not in source


def test_active_notebook_routes_entry_filters_through_canonical_helper():
    source = _notebook_code_source()

    assert (
        "from xauusd_ea.filters import passes_entry_filters as "
        "_passes_entry_filters_safe" in source
    )
    assert "def _safe_passes_filters(" in source
    assert "return _passes_entry_filters_safe(" in source
    assert 'registry=globals().get("entry_filters", {})' in source
    assert "if not _safe_passes_filters(df, signal_i, filters" in source


def test_active_notebook_routes_strategy_metrics_through_canonical_helper():
    source = _notebook_code_source()

    assert (
        "from xauusd_ea.metrics import clean_strategies as "
        "_clean_strategies_safe, compute_strategy_metrics as "
        "_compute_strategy_metrics_safe" in source
    )
    assert "return _compute_strategy_metrics_safe(" in source
    assert "return _clean_strategies_safe(" in source
    assert "profit_factor_raw = np.inf" not in source
    assert "profit_factor_for_score = min(" not in source
    assert "out = out[out[\"# Trades\"] >= int(min_trades)]" not in source


def test_active_notebook_routes_execution_costs_through_canonical_helpers():
    source = _notebook_cell_source(18)

    assert (
        "from xauusd_ea.execution import apply_execution_price as "
        "_apply_execution_price_safe" in source
    )
    assert "commission_per_side as _commission_per_side_safe" in source
    assert "spread_price as _spread_price_safe" in source
    assert "to_price_units as _to_price_units_safe" in source
    assert "return _to_price_units_safe(value, spec, friction)" in source
    assert "return _spread_price_safe(friction, spec)" in source
    assert (
        "return _apply_execution_price_safe(price, side, friction, spec, "
        "timestamp=timestamp)" in source
    )
    assert "return _commission_per_side_safe(lot, friction, spec)" in source
    assert "executed = price + spread + slip" not in source
    assert "return float(lot) * float(rt_rate) / 2.0" not in source


def test_active_notebook_has_no_competing_gross_pnl_implementation():
    source = _notebook_cell_source(18)

    assert "def _gross_pnl(" not in source
    assert "price_change * lot" not in source
    assert "close_position as _close_position_safe" in source


def test_active_notebook_routes_mark_to_market_through_canonical_helper():
    source = _notebook_cell_source(18)

    assert (
        "mark_to_market_equity as _mark_to_market_equity_safe" in source
    )
    assert "return _mark_to_market_equity_safe(" in source
    assert "exit_side = \"sell\" if direction == \"long\" else \"buy\"" not in source
    assert "return float(cash + gross - exit_commission)" not in source


def test_active_notebook_routes_position_close_through_canonical_helper():
    source = _notebook_cell_source(18)

    assert "close_position as _close_position_safe" in source
    assert "return _close_position_safe(" in source
    assert source.count("def _close_open_position(") == 1
    assert "trade_pnl = gross - open_pos[\"entry_commission\"]" not in source


def test_next_bar_entry_inputs_ignore_entry_bar_high_low_close():
    source = _notebook_cell_source(18)
    assert "entry_atr = float(atr_values[signal_i])" in source
    assert "atr_value=entry_atr" in source
    assert "def _calculate_lot(" in source

    run_backtest = _active_notebook_run_backtest()
    index = pd.date_range("2025-01-01", periods=6, freq="15min")
    original = pd.DataFrame(
        {
            "open": [100.0] * 6,
            "high": [101.0, 101.5, 102.0, 100.2, 100.2, 100.2],
            "low": [99.0, 99.5, 100.0, 99.8, 99.8, 99.8],
            "close": [100.0, 101.0, 101.0, 100.0, 100.0, 100.0],
            "volume": [1.0] * 6,
        },
        index=index,
    )
    mutated = original.copy()
    mutated.loc[index[3], ["high", "low", "close"]] = [150.0, 50.0, 130.0]

    long_signal = lambda frame: pd.Series(
        [False, False, True, False, False, False], index=frame.index
    )
    short_signal = lambda frame: pd.Series(False, index=frame.index)
    config = {
        "id": "closed_bar_entry_inputs",
        "entry": {
            "long_condition": long_signal,
            "short_condition": short_signal,
        },
        "params": {"ATR": {"period": 2}},
        "exit": {
            "atr_period": 2,
            "atr_multiplier": 1.0,
            "sl_type": "atr",
            "tp_type": "fib",
            "fib_levels": [1.618],
        },
        "sizing": {"sizing_method": "risk_percent", "risk_percent": 1.0},
        "friction": {},
    }

    original_trades, _, _ = run_backtest(
        config, original, execution_mode="next_bar_open"
    )
    mutated_trades, _, _ = run_backtest(
        config, mutated, execution_mode="next_bar_open"
    )

    assert original_trades and mutated_trades
    original_entry = original_trades[0]
    mutated_entry = mutated_trades[0]
    assert original_entry["signal_time"] == mutated_entry["signal_time"] == index[2]
    assert original_entry["entry_time"] == mutated_entry["entry_time"] == index[3]
    assert original_entry["entry_raw"] == mutated_entry["entry_raw"] == 100.0
    assert original_entry["stop_loss"] == pytest.approx(mutated_entry["stop_loss"])
    assert original_entry["lot"] == pytest.approx(mutated_entry["lot"])
    assert original_entry["take_profit"] == pytest.approx(
        mutated_entry["take_profit"]
    )


def test_active_notebook_inspect_path_requires_clean_export():
    inspect_cell = _notebook_cell_source(19)

    assert "Strict CLEAN strategy CSV not found" in inspect_cell
    assert 'source_type = "CLEAN"' in inspect_cell
    assert 'source_type = "SOFT"' not in inspect_cell
    assert 'source_type = "FALLBACK"' not in inspect_cell
    assert "elif os.path.exists(soft_csv)" not in inspect_cell
    assert "glob.glob(os.path.join(OUTPUT_ROOT, f\"**/*{RUN_ID}*.csv\"), recursive=True)" not in inspect_cell


def test_active_notebook_swap_path_uses_crossed_rollover_accounting():
    source = _notebook_code_source()

    assert (
        "book_crossed_rollover_swaps as _book_crossed_rollover_swaps_safe"
        in source
    )
    assert "_book_crossed_rollover_swaps(" in source
    assert "return _book_crossed_rollover_swaps_safe(" in source
    assert '"last_swap_check_time"' in source
    assert '"swap_cash": 0.0' in source
    assert "days_held = float(bars_held) / bars_per_day" not in source


def test_active_notebook_routes_broker_spec_through_verified_profile():
    source = _notebook_code_source()

    assert "from xauusd_ea.baseline import (" in source
    assert "merge_runtime_broker_overrides" in source
    assert "load_broker_profile(" in source
    assert "assert_runtime_broker_spec_matches_profile(" in source
    assert "XAUUSD_SPEC = assert_runtime_broker_spec_matches_profile({" in source
    assert '"symbol": "XAUUSD"' not in source
    assert '"contract_size": 100.0' not in source
    assert '"min_lot": 0.01' not in source
    assert '"max_lot": 50.0' not in source
    assert '"spread_points": 150' not in source
    assert '"commission_per_lot_round_turn": 7.0' not in source


def test_active_notebook_rejects_raw_broker_spec_dict_merges():
    source = _notebook_code_source()

    assert "{**XAUUSD_SPEC, **friction}" not in source
    assert '{**XAUUSD_SPEC, **es["sizing"]}' not in source
    assert '{**XAUUSD_SPEC, **(cfg2.get("friction", {}) or {})}' not in source
    assert '{**XAUUSD_SPEC, **(cfg2.get("sizing", {}) or {})}' not in source
    assert 'context="generate_strategy_configs.friction"' in source
    assert 'context="generate_strategy_configs.sizing"' in source
    assert 'context="_with_timeframe_friction.friction"' in source
    assert 'context="_with_timeframe_friction.sizing"' in source


def test_active_notebook_friction_helpers_do_not_fall_back_to_legacy_xauusd_cost_defaults():
    source = _notebook_code_source()

    assert "require_runtime_broker_spec" in source
    assert "merge_runtime_broker_overrides" in source
    assert 'runtime_spec = require_runtime_broker_spec(globals().get("XAUUSD_SPEC"))' in source
    assert 'runtime_spec = require_runtime_broker_spec(spec)' in source
    assert "commission_per_lot = config.get('commission_per_lot')" not in source
    assert "config.get('commission_per_lot', 7.0)" not in source
    assert "config.get('spread_points', 1.5)" not in source
    assert "config.get('swap_per_lot', -1.0)" not in source
    assert 'friction.get("commission_per_lot", 0.0)' not in source
    assert 'friction.get("spread_points", 0.0)' not in source
    assert 'friction.get("swap_per_lot", 0.0)' not in source
    assert 'cfg = merge_runtime_broker_overrides(runtime_spec, config, context=\'apply_commission\')' in source
    assert "context='apply_spread'" in source
    assert "allow_supported_spread_override=True" in source
    assert "context='apply_swap_cost'" in source
    assert 'point = runtime_spec[\'point\']' in source
    assert 'cost_value_mode = str(runtime_spec[\'cost_value_mode\']).lower()' in source
    assert "from xauusd_ea.execution import apply_execution_price" in source
    assert "return _apply_execution_price_safe(price, side, friction, spec, timestamp=timestamp)" in source
    assert "runtime_spec['commission_per_lot_round_turn']" in source
    assert "runtime_spec['spread_points']" in source
    assert "book_crossed_rollover_swaps as _book_crossed_rollover_swaps_safe" in source
    assert 'globals().get("XAUUSD_SPEC", {})' not in source
    assert "point = config.get('point', runtime_spec['point'])" not in source
    assert "cost_value_mode = str(config.get('cost_value_mode', runtime_spec['cost_value_mode'])).lower()" not in source
    assert "daily_swap = config.get('swap_per_lot', runtime_spec['swap_per_lot'])" not in source


def test_active_notebook_short_cost_paths_use_directional_swap_and_active_spec():
    source = _notebook_code_source()

    assert "def _swap_cash(" not in source
    assert "crossed_rollover_swap_cash(" not in source
    assert "return _book_crossed_rollover_swaps_safe(" in source
    assert "_book_crossed_rollover_swaps(cash, open_pos, ts, friction, broker_spec)" in source
    assert "_close_position_safe(open_pos, exit_raw" in source
    assert 'swap_cash = float(open_pos.get("swap_cash", 0.0))' not in source
    assert "_commission_per_side(lot, friction, broker_spec)" in source
    assert '_swap_cash(open_pos["lot"], bars_held, friction)' not in source
    assert '_commission_per_side(open_pos["lot"], friction)' not in source


def test_active_notebook_lot_sizing_uses_verified_micro_defaults_and_no_round_up():
    source = _notebook_code_source()

    assert (
        "from xauusd_ea.sizing import calculate_position_size as "
        "_calculate_position_size_safe" in source
    )
    assert "return _calculate_position_size_safe(" in source
    assert "_calculate_lot(cash, entry_exec, stop_loss, sizing_cfg, atr_value=entry_atr, spec=broker_spec)" in source
    assert 'cfg["atr"] = atr_value' in source
    assert "runtime_spec=runtime_spec" in source
    assert "risk_amount = (risk_percent / 100.0) * capital" not in source
    assert "steps = int((lot_size - min_lot) / lot_step + 1e-12)" not in source
    assert 'round(round(lot / step) * step, precision)' not in source
    assert 'lot_size = max(min_lot, min(lot_size, max_lot))' not in source
    assert 'contract_size = config.get("contract_size", runtime_spec["contract_size"])' not in source
    assert 'min_lot = config.get("min_lot", runtime_spec["min_lot"])' not in source
    assert 'contract_size = kwargs.get("contract_size", runtime_spec["contract_size"])' not in source
    assert 'min_lot = kwargs.get("min_lot", runtime_spec["min_lot"])' not in source
    assert 'cfg = {**runtime_spec, **(sizing_cfg or {})}' not in source
    assert 'lot_raw = cfg.get("fixed_lot", cfg.get("base_lot_size", runtime_spec["min_lot"]))' not in source


def test_active_notebook_has_no_stale_legacy_outputs_or_full_sample_fallback_text():
    notebook_text = NOTEBOOK.read_text(encoding="utf-8")

    assert "falling back to full-sample evaluation" not in notebook_text
    assert "'symbol': 'XAUUSD'" not in notebook_text
    assert "'contract_size': 100.0" not in notebook_text
    assert "'min_lot': 0.01" not in notebook_text
    assert "'max_lot': 50.0" not in notebook_text
    assert "'spread_points': 1.5" not in notebook_text
    assert "'spread_points': 150" not in notebook_text
    assert "'commission_per_lot': 7.0" not in notebook_text
    assert "'commission_per_lot_round_turn': 7.0" not in notebook_text
    assert "'swap_per_lot': -1.0" not in notebook_text


@pytest.mark.parametrize(
    ("timeframe", "filename", "expected_split", "expected_sample_end", "expected_holdout_start"),
    [
        ("M15", "XAUUSD_M15.csv", 57246, "2025-06-05 06:45:00", "2025-06-05 07:00:00"),
        ("M30", "XAUUSD_M30.csv", 28625, "2025-06-05 06:30:00", "2025-06-05 07:00:00"),
        ("H1", "XAUUSD_H1.csv", 14321, "2025-06-05 05:00:00", "2025-06-05 06:00:00"),
        ("H4", "XAUUSD_H4.csv", 3746, "2025-06-04 20:00:00", "2025-06-05 00:00:00"),
    ],
)
def test_split_sample_holdout_matches_real_dataset_boundaries(
    timeframe: str,
    filename: str,
    expected_split: int,
    expected_sample_end: str,
    expected_holdout_start: str,
):
    df = load_mt5_csv(ROOT / filename)

    split = split_sample_holdout(df, timeframe=timeframe, sample_ratio=0.70)

    assert split.split_index == expected_split
    assert split.sample_start == df.index[0]
    assert split.sample_end == pd.Timestamp(expected_sample_end)
    assert split.holdout_start == pd.Timestamp(expected_holdout_start)
    assert split.holdout_end == df.index[-1]
    assert len(split.sample) + len(split.holdout) == len(df)


@pytest.mark.parametrize("ratio", [0.49, 0.91])
def test_split_sample_holdout_rejects_ratio_outside_audited_bounds(ratio: float):
    df = _make_timeframe_df(periods=10)

    with pytest.raises(UnsafeEvaluationError, match="audited range"):
        split_sample_holdout(df, timeframe="M15", sample_ratio=ratio)


def test_split_sample_holdout_rejects_unsorted_or_duplicate_timestamps():
    unsorted_df = _make_timeframe_df(periods=5).sort_index(ascending=False)
    with pytest.raises(UnsafeEvaluationError, match="sorted timestamps"):
        split_sample_holdout(unsorted_df, timeframe="M15", sample_ratio=0.70)

    duplicate_df = _make_timeframe_df(periods=5)
    duplicate_df.index = pd.DatetimeIndex(list(duplicate_df.index[:4]) + [duplicate_df.index[3]])
    with pytest.raises(UnsafeEvaluationError, match="unique timestamps"):
        split_sample_holdout(duplicate_df, timeframe="M15", sample_ratio=0.70)


def test_split_sample_holdout_rejects_missing_holdout_rows():
    df = _make_timeframe_df(periods=3)

    with pytest.raises(UnsafeEvaluationError, match="need at least 4"):
        split_sample_holdout(
            df,
            timeframe="M15",
            sample_ratio=0.70,
            min_sample_rows=2,
            min_holdout_rows=2,
        )


def test_split_sample_holdout_rejects_ratio_that_requires_boundary_clipping():
    df = _make_timeframe_df(periods=5)

    with pytest.raises(
        UnsafeEvaluationError, match="cannot satisfy the required minimum rows"
    ):
        split_sample_holdout(
            df,
            timeframe="M15",
            sample_ratio=0.90,
            min_sample_rows=2,
            min_holdout_rows=2,
        )


def test_plan_walk_forward_windows_produces_chronological_non_overlapping_windows():
    df = _make_timeframe_df(periods=12)

    windows = plan_walk_forward_windows(
        df,
        timeframe="M15",
        train_window=4,
        test_window=2,
        step_size=2,
    )

    assert all(isinstance(window, WalkForwardWindow) for window in windows)
    assert [(w.train_start, w.train_end, w.test_start, w.test_end) for w in windows] == [
        (0, 4, 4, 6),
        (2, 6, 6, 8),
        (4, 8, 8, 10),
        (6, 10, 10, 12),
    ]
    assert windows[0].train_start_time == df.index[0]
    assert windows[0].train_end_time == df.index[3]
    assert windows[0].test_start_time == df.index[4]
    assert windows[0].test_end_time == df.index[5]
    assert all(window.train_end == window.test_start for window in windows)


def test_plan_walk_forward_windows_rejects_insufficient_rows_without_fallback():
    df = _make_timeframe_df(periods=5)

    with pytest.raises(UnsafeEvaluationError, match="not enough rows"):
        plan_walk_forward_windows(
            df,
            timeframe="M15",
            train_window=4,
            test_window=2,
            step_size=1,
        )


def test_plan_walk_forward_windows_rejects_invalid_index_or_parameters():
    unsorted_df = _make_timeframe_df(periods=8).sort_index(ascending=False)
    with pytest.raises(UnsafeEvaluationError, match="sorted timestamps"):
        plan_walk_forward_windows(
            unsorted_df,
            timeframe="M15",
            train_window=4,
            test_window=2,
            step_size=1,
        )

    df = _make_timeframe_df(periods=8)
    with pytest.raises(ValueError, match="must be positive"):
        plan_walk_forward_windows(
            df,
            timeframe="M15",
            train_window=0,
            test_window=2,
            step_size=1,
        )


def test_plan_walk_forward_windows_matches_real_h4_dataset_boundaries():
    df = load_mt5_csv(ROOT / "XAUUSD_H4.csv")

    windows = plan_walk_forward_windows(
        df,
        timeframe="H4",
        train_window=750,
        test_window=125,
        step_size=60,
        min_windows=2,
    )

    assert len(windows) == 75
    assert windows[0].train_start_time == pd.Timestamp("2023-01-03 00:00:00")
    assert windows[0].train_end_time == pd.Timestamp("2023-06-27 20:00:00")
    assert windows[0].test_start_time == pd.Timestamp("2023-06-28 00:00:00")
    assert windows[0].test_end_time == pd.Timestamp("2023-07-26 16:00:00")
    assert windows[-1].train_start == 4440
    assert windows[-1].test_end == 5315
    assert windows[-1].test_end_time == pd.Timestamp("2026-06-11 12:00:00")


def test_research_config_fingerprint_ignores_runtime_forward_metadata():
    sample_config = {
        "id": "sample_M15_001",
        "timeframe": "M15",
        "indicators": ["ema", "atr"],
        "params": {"ema_fast": 12, "ema_slow": 26, "risk_percent": 0.5},
        "sizing": {"mode": "risk_percent", "risk_percent": 0.5},
    }
    forward_config = {
        **sample_config,
        "sample_strategy_id": "sample_M15_001",
        "sample_config_path": str(ROOT / "tmp" / "config.pkl"),
        "sample_rank": 1,
        "Phase": "EXACT_OOS_AGG",
    }

    assert research_config_fingerprint(sample_config) == research_config_fingerprint(
        forward_config
    )
    assert_exact_forward_config_identity(sample_config, forward_config)


def test_assert_expected_research_config_fingerprint_accepts_matching_hash():
    sample_config = {
        "id": "sample_match_001",
        "timeframe": "M15",
        "params": {"ema_fast": 12, "ema_slow": 26},
    }
    expected = research_config_fingerprint(sample_config)

    assert (
        assert_expected_research_config_fingerprint(expected, sample_config) == expected
    )


def test_assert_expected_research_config_fingerprint_rejects_missing_hash():
    sample_config = {
        "id": "sample_missing_fp",
        "timeframe": "H1",
        "params": {"rr": 1.5},
    }

    with pytest.raises(UnsafeEvaluationError, match="requires the sample-selected"):
        assert_expected_research_config_fingerprint("", sample_config)


def test_assert_expected_research_config_fingerprint_rejects_mutated_config():
    sample_config = {
        "id": "sample_fp_002",
        "timeframe": "M30",
        "params": {"ema_fast": 12, "ema_slow": 26, "risk_percent": 0.5},
    }
    mutated = {
        **sample_config,
        "params": {"ema_fast": 10, "ema_slow": 26, "risk_percent": 0.5},
    }
    expected = research_config_fingerprint(sample_config)

    with pytest.raises(UnsafeEvaluationError, match="fingerprint mismatch"):
        assert_expected_research_config_fingerprint(expected, mutated)


def test_exact_forward_config_identity_rejects_research_parameter_changes():
    sample_config = {
        "id": "sample_H1_002",
        "timeframe": "H1",
        "indicators": ["ema", "atr"],
        "params": {"ema_fast": 12, "ema_slow": 26, "risk_percent": 0.5},
        "exits": {"rr": 1.0},
    }
    forward_config = {
        **sample_config,
        "params": {"ema_fast": 10, "ema_slow": 26, "risk_percent": 0.5},
        "sample_strategy_id": "sample_H1_002",
    }

    with pytest.raises(UnsafeEvaluationError, match="Exact forward config mismatch"):
        assert_exact_forward_config_identity(sample_config, forward_config)


def test_exact_forward_config_identity_does_not_ignore_nested_research_params():
    sample_config = {
        "id": "sample_M30_003",
        "timeframe": "M30",
        "params": {"ema_fast": 12, "window_id": 5},
        "filters": {"session": {"window_id": "london_open"}},
    }
    forward_config = {
        **sample_config,
        "params": {"ema_fast": 12, "window_id": 6},
    }

    with pytest.raises(UnsafeEvaluationError, match="Exact forward config mismatch"):
        assert_exact_forward_config_identity(sample_config, forward_config)


def test_exact_forward_config_identity_treats_top_level_window_id_as_research_data():
    sample_config = {
        "id": "sample_M30_window",
        "timeframe": "M30",
        "window_id": 5,
        "params": {"ema_fast": 12},
    }
    forward_config = {
        **sample_config,
        "window_id": 6,
    }

    with pytest.raises(UnsafeEvaluationError, match="Exact forward config mismatch"):
        assert_exact_forward_config_identity(sample_config, forward_config)


def test_exact_forward_config_identity_allows_explicit_nested_metadata_exemptions():
    sample_config = {
        "id": "sample_M30_004",
        "timeframe": "M30",
        "params": {"ema_fast": 12, "window_id": 5},
        "runtime_metadata": {"loaded_window_id": "london_open"},
    }
    forward_config = {
        **sample_config,
        "params": {"ema_fast": 12, "window_id": 5},
        "runtime_metadata": {"loaded_window_id": "new_runtime_window"},
    }

    assert_exact_forward_config_identity(
        sample_config,
        forward_config,
        ignored_paths={("runtime_metadata", "loaded_window_id")},
    )


def test_exact_forward_config_identity_rejects_structured_metadata_exemptions():
    sample_config = {
        "id": "sample_M30_004",
        "timeframe": "M30",
        "params": {"ema_fast": 12, "window_id": 5},
        "runtime_metadata": {
            "loaded_window": {"id": "london_open", "ema_fast": 12},
        },
    }
    forward_config = {
        **sample_config,
        "runtime_metadata": {
            "loaded_window": {"id": "new_runtime_window", "ema_fast": 10},
        },
    }

    with pytest.raises(
        UnsafeEvaluationError, match="must point to scalar leaf values"
    ):
        assert_exact_forward_config_identity(
            sample_config,
            forward_config,
            ignored_paths={("runtime_metadata", "loaded_window")},
        )


def test_exact_forward_config_identity_rejects_broad_metadata_root_exemptions():
    with pytest.raises(UnsafeEvaluationError, match="target specific metadata fields"):
        assert_exact_forward_config_identity(
            {"runtime_metadata": {"loaded_window_id": "a"}},
            {"runtime_metadata": {"loaded_window_id": "b"}},
            ignored_paths={("runtime_metadata",)},
        )


def test_exact_forward_config_identity_rejects_nested_exemptions_for_research_paths():
    sample_config = {
        "id": "sample_M30_004",
        "timeframe": "M30",
        "params": {"ema_fast": 12, "window_id": 5},
    }
    forward_config = {
        **sample_config,
        "params": {"ema_fast": 10, "window_id": 5},
    }

    with pytest.raises(
        UnsafeEvaluationError, match="nested ignores are restricted to audited runtime metadata roots"
    ):
        assert_exact_forward_config_identity(
            sample_config,
            forward_config,
            ignored_paths={("params", "ema_fast")},
        )


def test_exact_forward_config_identity_rejects_top_level_research_key_exemptions():
    sample_config = {
        "id": "sample_M30_004",
        "timeframe": "M30",
        "params": {"ema_fast": 12},
    }
    forward_config = {
        **sample_config,
        "params": {"ema_fast": 10},
    }

    with pytest.raises(
        UnsafeEvaluationError, match="audited top-level runtime metadata"
    ):
        assert_exact_forward_config_identity(
            sample_config,
            forward_config,
            ignored_keys={"params"},
        )


def test_exact_forward_config_identity_ignores_recorded_fingerprint_metadata():
    sample_config = {"id": "sample_M15_005", "timeframe": "M15", "params": {"ema_fast": 12}}
    forward_config = {
        **sample_config,
        "sample_strategy_id": "sample_M15_005",
        "sample_config_fingerprint": "sha256:placeholder",
    }

    assert_exact_forward_config_identity(sample_config, forward_config)


def test_exact_forward_config_identity_rejects_non_finite_values():
    sample_config = {"id": "sample_H4_003", "timeframe": "H4", "params": {"rr": 1.0}}
    forward_config = {"id": "sample_H4_003", "timeframe": "H4", "params": {"rr": float("nan")}}

    with pytest.raises(UnsafeEvaluationError, match="non-finite"):
        research_config_fingerprint(forward_config)
    with pytest.raises(UnsafeEvaluationError, match="non-finite"):
        assert_exact_forward_config_identity(sample_config, forward_config)


def test_research_config_fingerprint_normalizes_numpy_scalar_values():
    sample_config = {
        "id": "sample_np_001",
        "timeframe": "H1",
        "params": {
            "ema_fast": np.int64(12),
            "risk_percent": np.float64(0.5),
            "enabled": np.bool_(True),
        },
    }
    native_config = {
        "id": "sample_np_001",
        "timeframe": "H1",
        "params": {
            "ema_fast": 12,
            "risk_percent": 0.5,
            "enabled": True,
        },
    }

    assert research_config_fingerprint(sample_config) == research_config_fingerprint(
        native_config
    )
    assert_exact_forward_config_identity(sample_config, native_config)
