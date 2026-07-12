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
    resolve_intrabar_stop_target,
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
        "_intrabar_stop_target_safe": resolve_intrabar_stop_target,
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


def test_active_notebook_routes_intrabar_exits_through_canonical_helper():
    active_source = _notebook_cell_source(18)

    assert "resolve_intrabar_stop_target as _intrabar_stop_target_safe" in active_source
    assert active_source.count("_intrabar_stop_target_safe(") == 2
    assert "_intrabar_stop_target(" not in active_source
    assert "_intrabar_stop_target_safe(open_pos, bar_open," in active_source


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


def test_active_notebook_routes_position_close_through_canonißÝ;¶‰žËkºwµçU}¹½Ñ•‰½½­}¡…Í}¹½}ÍÑ…±•}±•…å}½ÕÑÁÕÑÍ}½É}™Õ±±}Í…µÁ±•}™…±±‰…­}Ñ•áÐ ¤è4(€€€¹½Ñ•‰½½­}Ñ•áÐ€ô9=Q	==,¹É•…‘}Ñ•áÐ¡•¹½‘¥¹œô‰ÕÑ˜´àˆ¤4(4(€€€…ÍÍ•ÉÐ€‰™…±±¥¹œ‰…¬Ñ¼™Õ±°µÍ…µÁ±”•Ù…±Õ…Ñ¥½¸ˆ¹½Ð¥¸¹½Ñ•‰½½­}Ñ•áÐ4(€€€…ÍÍ•ÉÐ€ˆÍåµ‰½°œè€aUUMœˆ¹½Ð¥¸¹½Ñ•‰½½­}Ñ•áÐ4(€€€…ÍÍ•ÉÐ€ˆ½¹ÑÉ…Ñ}Í¥é”œè€ÄÀÀ¸Àˆ¹½Ð¥¸¹½Ñ•‰½½­}Ñ•áÐ4(€€€…ÍÍ•ÉÐ€ˆµ¥¹}±½Ðœè€À¸ÀÄˆ¹½Ð¥¸¹½Ñ•‰½½­}Ñ•áÐ4(€€€…ÍÍ•ÉÐ€ˆµ…á}±½Ðœè€ÔÀ¸Àˆ¹½Ð¥¸¹½Ñ•‰½½­}Ñ•áÐ4(€€€…ÍÍ•ÉÐ€ˆÍÁÉ•…‘}Á½¥¹ÑÌœè€Ä¸Ôˆ¹½Ð¥¸¹½Ñ•‰½½­}Ñ•áÐ4(€€€…ÍÍ•ÉÐ€ˆÍÁÉ•…‘}Á½¥¹ÑÌœè€ÄÔÀˆ¹½Ð¥¸¹½Ñ•‰½½­}Ñ•áÐ4(€€€…ÍÍ•ÉÐ€ˆ½µµ¥ÍÍ¥½¹}Á•É}±½Ðœè€Ü¸Àˆ¹½Ð¥¸¹½Ñ•‰½½­}Ñ•áÐ4(€€€…ÍÍ•ÉÐ€ˆ½µµ¥ÍÍ¥½¹}Á•É}±½Ñ}É½Õ¹‘}ÑÕÉ¸œè€Ü¸Àˆ¹½Ð¥¸¹½Ñ•‰½½­}Ñ•áÐ4(€€€…ÍÍ•ÉÐ€ˆÍÝ…Á}Á•É}±½Ðœè€´Ä¸Àˆ¹½Ð¥¸¹½Ñ•‰½½­}Ñ•áÐ4(4(4)ÁåÑ•ÍÐ¹µ…É¬¹Á…É…µ•ÑÉ¥é” 4(€€€€ ‰Ñ¥µ•™É…µ”ˆ°€‰™¥±•¹…µ”ˆ°€‰•áÁ•Ñ•‘}ÍÁ±¥Ðˆ°€‰•áÁ•Ñ•‘}Í…µÁ±•}•¹ˆ°€‰•áÁ•Ñ•‘}¡½±‘½ÕÑ}ÍÑ…ÉÐˆ¤°4(€€€l4(€€€€€€€€ ‰4ÄÔˆ°€‰aUUM}4ÄÔ¹ÍØˆ°€ÔÜÈÐØ°€ˆÈÀÈÔ´ÀØ´ÀÔ€ÀØèÐÔèÀÀˆ°€ˆÈÀÈÔ´ÀØ´ÀÔ€ÀÜèÀÀèÀÀˆ¤°4(€€€€€€€€ ‰4ÌÀˆ°€‰aUUM}4ÌÀ¹ÍØˆ°€ÈàØÈÔ°€ˆÈÀÈÔ´ÀØ´ÀÔ€ÀØèÌÀèÀÀˆ°€ˆÈÀÈÔ´ÀØ´ÀÔ€ÀÜèÀÀèÀÀˆ¤°4(€€€€€€€€ ‰ Äˆ°€‰aUUM} Ä¹ÍØˆ°€ÄÐÌÈÄ°€ˆÈÀÈÔ´ÀØ´ÀÔ€ÀÔèÀÀèÀÀˆ°€ˆÈÀÈÔ´ÀØ´ÀÔ€ÀØèÀÀèÀÀˆ¤°4(€€€€€€€€ ‰ Ðˆ°€‰aUUM} Ð¹ÍØˆ°€ÌÜÐØ°€ˆÈÀÈÔ´ÀØ´ÀÐ€ÈÀèÀÀèÀÀˆ°€ˆÈÀÈÔ´ÀØ´ÀÔ€ÀÀèÀÀèÀÀˆ¤°4(€€€t°4(¤4)‘•˜Ñ•ÍÑ}ÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÑ}µ…Ñ¡•Í}É•…±}‘…Ñ…Í•Ñ}‰½Õ¹‘…É¥•Ì 4(€€€Ñ¥µ•™É…µ”èÍÑÈ°4(€€€™¥±•¹…µ”èÍÑÈ°4(€€€•áÁ•Ñ•‘}ÍÁ±¥Ðè¥¹Ð°4(€€€•áÁ•Ñ•‘}Í…µÁ±•}•¹èÍÑÈ°4(€€€•áÁ•Ñ•‘}¡½±‘½ÕÑ}ÍÑ…ÉÐèÍÑÈ°4(¤è4(€€€‘˜€ô±½…‘}µÐÕ}ÍØ¡I==P€¼™¥±•¹…µ”¤4(4(€€€ÍÁ±¥Ð€ôÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÐ¡‘˜°Ñ¥µ•™É…µ”õÑ¥µ•™É…µ”°Í…µÁ±•}É…Ñ¥¼ôÀ¸ÜÀ¤4(4(€€€…ÍÍ•ÉÐÍÁ±¥Ð¹ÍÁ±¥Ñ}¥¹‘•à€ôô•áÁ•Ñ•‘}ÍÁ±¥Ð4(€€€…ÍÍ•ÉÐÍÁ±¥Ð¹Í…µÁ±•}ÍÑ…ÉÐ€ôô‘˜¹¥¹‘•álÁt4(€€€…ÍÍ•ÉÐÍÁ±¥Ð¹Í…µÁ±•}•¹€ôôÁ¹Q¥µ•ÍÑ…µÀ¡•áÁ•Ñ•‘}Í…µÁ±•}•¹¤4(€€€…ÍÍ•ÉÐÍÁ±¥Ð¹¡½±‘½ÕÑ}ÍÑ…ÉÐ€ôôÁ¹Q¥µ•ÍÑ…µÀ¡•áÁ•Ñ•‘}¡½±‘½ÕÑ}ÍÑ…ÉÐ¤4(€€€…ÍÍ•ÉÐÍÁ±¥Ð¹¡½±‘½ÕÑ}•¹€ôô‘˜¹¥¹‘•ál´Åt4(€€€…ÍÍ•ÉÐ±•¸¡ÍÁ±¥Ð¹Í…µÁ±”¤€¬±•¸¡ÍÁ±¥Ð¹¡½±‘½ÕÐ¤€ôô±•¸¡‘˜¤4(4(4)ÁåÑ•ÍÐ¹µ…É¬¹Á…É…µ•ÑÉ¥é” ‰É…Ñ¥¼ˆ°lÀ¸Ðä°€À¸äÅt¤4)‘•˜Ñ•ÍÑ}ÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÑ}É•©•ÑÍ}É…Ñ¥½}½ÕÑÍ¥‘•}…Õ‘¥Ñ•‘}‰½Õ¹‘Ì¡É…Ñ¥¼è™±½…Ð¤è4(€€€‘˜€ô}µ…­•}Ñ¥µ•™É…µ•}‘˜¡Á•É¥½‘ÌôÄÀ¤4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰…Õ‘¥Ñ•É…¹”ˆ¤è4(€€€€€€€ÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÐ¡‘˜°Ñ¥µ•™É…µ”ô‰4ÄÔˆ°Í…µÁ±•}É…Ñ¥¼õÉ…Ñ¥¼¤4(4(4)‘•˜Ñ•ÍÑ}ÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÑ}É•©•ÑÍ}Õ¹Í½ÉÑ•‘}½É}‘ÕÁ±¥…Ñ•}Ñ¥µ•ÍÑ…µÁÌ ¤è4(€€€Õ¹Í½ÉÑ•‘}‘˜€ô}µ…­•}Ñ¥µ•™É…µ•}‘˜¡Á•É¥½‘ÌôÔ¤¹Í½ÉÑ}¥¹‘•à¡…Í•¹‘¥¹œõ…±Í”¤4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰Í½ÉÑ•Ñ¥µ•ÍÑ…µÁÌˆ¤è4(€€€€€€€ÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÐ¡Õ¹Í½ÉÑ•‘}‘˜°Ñ¥µ•™É…µ”ô‰4ÄÔˆ°Í…µÁ±•}É…Ñ¥¼ôÀ¸ÜÀ¤4(4(€€€‘ÕÁ±¥…Ñ•}‘˜€ô}µ…­•}Ñ¥µ•™É…µ•}‘˜¡Á•É¥½‘ÌôÔ¤4(€€€‘ÕÁ±¥…Ñ•}‘˜¹¥¹‘•à€ôÁ¹…Ñ•Ñ¥µ•%¹‘•à¡±¥ÍÐ¡‘ÕÁ±¥…Ñ•}‘˜¹¥¹‘•álèÑt¤€¬m‘ÕÁ±¥…Ñ•}‘˜¹¥¹‘•álÍut¤4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰Õ¹¥ÅÕ”Ñ¥µ•ÍÑ…µÁÌˆ¤è4(€€€€€€€ÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÐ¡‘ÕÁ±¥…Ñ•}‘˜°Ñ¥µ•™É…µ”ô‰4ÄÔˆ°Í…µÁ±•}É…Ñ¥¼ôÀ¸ÜÀ¤4(4(4)‘•˜Ñ•ÍÑ}ÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÑ}É•©•ÑÍ}µ¥ÍÍ¥¹}¡½±‘½ÕÑ}É½ÝÌ ¤è4(€€€‘˜€ô}µ…­•}Ñ¥µ•™É…µ•}‘˜¡Á•É¥½‘ÌôÌ¤4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰¹••…Ð±•…ÍÐ€Ðˆ¤è4(€€€€€€€ÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÐ 4(€€€€€€€€€€€‘˜°4(€€€€€€€€€€€Ñ¥µ•™É…µ”ô‰4ÄÔˆ°4(€€€€€€€€€€€Í…µÁ±•}É…Ñ¥¼ôÀ¸ÜÀ°4(€€€€€€€€€€€µ¥¹}Í…µÁ±•}É½ÝÌôÈ°4(€€€€€€€€€€€µ¥¹}¡½±‘½ÕÑ}É½ÝÌôÈ°4(€€€€€€€€¤4(4(4)‘•˜Ñ•ÍÑ}ÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÑ}É•©•ÑÍ}É…Ñ¥½}Ñ¡…Ñ}É•ÅÕ¥É•Í}‰½Õ¹‘…Éå}±¥ÁÁ¥¹œ ¤è4(€€€‘˜€ô}µ…­•}Ñ¥µ•™É…µ•}‘˜¡Á•É¥½‘ÌôÔ¤4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì 4(€€€€€€€U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰…¹¹½ÐÍ…Ñ¥Í™äÑ¡”É•ÅÕ¥É•µ¥¹¥µÕ´É½ÝÌˆ4(€€€€¤è4(€€€€€€€ÍÁ±¥Ñ}Í…µÁ±•}¡½±‘½ÕÐ 4(€€€€€€€€€€€‘˜°4(€€€€€€€€€€€Ñ¥µ•™É…µ”ô‰4ÄÔˆ°4(€€€€€€€€€€€Í…µÁ±•}É…Ñ¥¼ôÀ¸äÀ°4(€€€€€€€€€€€µ¥¹}Í…µÁ±•}É½ÝÌôÈ°4(€€€€€€€€€€€µ¥¹}¡½±‘½ÕÑ}É½ÝÌôÈ°4(€€€€€€€€¤4(4(4)‘•˜Ñ•ÍÑ}Á±…¹}Ý…±­}™½ÉÝ…É‘}Ý¥¹‘½ÝÍ}ÁÉ½‘Õ•Í}¡É½¹½±½¥…±}¹½¹}½Ù•É±…ÁÁ¥¹}Ý¥¹‘½ÝÌ ¤è4(€€€‘˜€ô}µ…­•}Ñ¥µ•™É…µ•}‘˜¡Á•É¥½‘ÌôÄÈ¤4(4(€€€Ý¥¹‘½ÝÌ€ôÁ±…¹}Ý…±­}™½ÉÝ…É‘}Ý¥¹‘½ÝÌ 4(€€€€€€€‘˜°4(€€€€€€€Ñ¥µ•™É…µ”ô‰4ÄÔˆ°4(€€€€€€€ÑÉ…¥¹}Ý¥¹‘½ÜôÐ°4(€€€€€€€Ñ•ÍÑ}Ý¥¹‘½ÜôÈ°4(€€€€€€€ÍÑ•Á}Í¥é”ôÈ°4(€€€€¤4(4(€€€…ÍÍ•ÉÐ…±°¡¥Í¥¹ÍÑ…¹”¡Ý¥¹‘½Ü°]…±­½ÉÝ…É‘]¥¹‘½Ü¤™½ÈÝ¥¹‘½Ü¥¸Ý¥¹‘½ÝÌ¤4(€€€…ÍÍ•ÉÐl¡Ü¹ÑÉ…¥¹}ÍÑ…ÉÐ°Ü¹ÑÉ…¥¹}•¹°Ü¹Ñ•ÍÑ}ÍÑ…ÉÐ°Ü¹Ñ•ÍÑ}•¹¤™½ÈÜ¥¸Ý¥¹‘½ÝÍt€ôôl4(€€€€€€€€ À°€Ð°€Ð°€Ø¤°4(€€€€€€€€ È°€Ø°€Ø°€à¤°4(€€€€€€€€ Ð°€à°€à°€ÄÀ¤°4(€€€€€€€€ Ø°€ÄÀ°€ÄÀ°€ÄÈ¤°4(€€€t4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍlÁt¹ÑÉ…¥¹}ÍÑ…ÉÑ}Ñ¥µ”€ôô‘˜¹¥¹‘•álÁt4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍlÁt¹ÑÉ…¥¹}•¹‘}Ñ¥µ”€ôô‘˜¹¥¹‘•álÍt4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍlÁt¹Ñ•ÍÑ}ÍÑ…ÉÑ}Ñ¥µ”€ôô‘˜¹¥¹‘•álÑt4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍlÁt¹Ñ•ÍÑ}•¹‘}Ñ¥µ”€ôô‘˜¹¥¹‘•álÕt4(€€€…ÍÍ•ÉÐ…±°¡Ý¥¹‘½Ü¹ÑÉ…¥¹}•¹€ôôÝ¥¹‘½Ü¹Ñ•ÍÑ}ÍÑ…ÉÐ™½ÈÝ¥¹‘½Ü¥¸Ý¥¹‘½ÝÌ¤4(4(4)‘•˜Ñ•ÍÑ}Á±…¹}Ý…±­}™½ÉÝ…É‘}Ý¥¹‘½ÝÍ}É•©•ÑÍ}¥¹ÍÕ™™¥¥•¹Ñ}É½ÝÍ}Ý¥Ñ¡½ÕÑ}™…±±‰…¬ ¤è4(€€€‘˜€ô}µ…­•}Ñ¥µ•™É…µ•}‘˜¡Á•É¥½‘ÌôÔ¤4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰¹½Ð•¹½Õ É½ÝÌˆ¤è4(€€€€€€€Á±…¹}Ý…±­}™½ÉÝ…É‘}Ý¥¹‘½ÝÌ 4(€€€€€€€€€€€‘˜°4(€€€€€€€€€€€Ñ¥µ•™É…µ”ô‰4ÄÔˆ°4(€€€€€€€€€€€ÑÉ…¥¹}Ý¥¹‘½ÜôÐ°4(€€€€€€€€€€€Ñ•ÍÑ}Ý¥¹‘½ÜôÈ°4(€€€€€€€€€€€ÍÑ•Á}Í¥é”ôÄ°4(€€€€€€€€¤4(4(4)‘•˜Ñ•ÍÑ}Á±…¹}Ý…±­}™½ÉÝ…É‘}Ý¥¹‘½ÝÍ}É•©•ÑÍ}¥¹Ù…±¥‘}¥¹‘•á}½É}Á…É…µ•Ñ•ÉÌ ¤è4(€€€Õ¹Í½ÉÑ•‘}‘˜€ô}µ…­•}Ñ¥µ•™É…µ•}‘˜¡Á•É¥½‘Ìôà¤¹Í½ÉÑ}¥¹‘•à¡…Í•¹‘¥¹œõ…±Í”¤4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰Í½ÉÑ•Ñ¥µ•ÍÑ…µÁÌˆ¤è4(€€€€€€€Á±…¹}Ý…±­}™½ÉÝ…É‘}Ý¥¹‘½ÝÌ 4(€€€€€€€€€€€Õ¹Í½ÉÑ•‘}‘˜°4(€€€€€€€€€€€Ñ¥µ•™É…µ”ô‰4ÄÔˆ°4(€€€€€€€€€€€ÑÉ…¥¹}Ý¥¹‘½ÜôÐ°4(€€€€€€€€€€€Ñ•ÍÑ}Ý¥¹‘½ÜôÈ°4(€€€€€€€€€€€ÍÑ•Á}Í¥é”ôÄ°4(€€€€€€€€¤4(4(€€€‘˜€ô}µ…­•}Ñ¥µ•™É…µ•}‘˜¡Á•É¥½‘Ìôà¤4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡Y…±Õ•ÉÉ½È°µ…Ñ ô‰µÕÍÐ‰”Á½Í¥Ñ¥Ù”ˆ¤è4(€€€€€€€Á±…¹}Ý…±­}™½ÉÝ…É‘}Ý¥¹‘½ÝÌ 4(€€€€€€€€€€€‘˜°4(€€€€€€€€€€€Ñ¥µ•™É…µ”ô‰4ÄÔˆ°4(€€€€€€€€€€€ÑÉ…¥¹}Ý¥¹‘½ÜôÀ°4(€€€€€€€€€€€Ñ•ÍÑ}Ý¥¹‘½ÜôÈ°4(€€€€€€€€€€€ÍÑ•Á}Í¥é”ôÄ°4(€€€€€€€€¤4(4(4)‘•˜Ñ•ÍÑ}Á±…¹}Ý…±­}™½ÉÝ…É‘}Ý¥¹‘½ÝÍ}µ…Ñ¡•Í}É•…±} Ñ}‘…Ñ…Í•Ñ}‰½Õ¹‘…É¥•Ì ¤è4(€€€‘˜€ô±½…‘}µÐÕ}ÍØ¡I==P€¼€‰aUUM} Ð¹ÍØˆ¤4(4(€€€Ý¥¹‘½ÝÌ€ôÁ±…¹}Ý…±­}™½ÉÝ…É‘}Ý¥¹‘½ÝÌ 4(€€€€€€€‘˜°4(€€€€€€€Ñ¥µ•™É…µ”ô‰ Ðˆ°4(€€€€€€€ÑÉ…¥¹}Ý¥¹‘½ÜôÜÔÀ°4(€€€€€€€Ñ•ÍÑ}Ý¥¹‘½ÜôÄÈÔ°4(€€€€€€€ÍÑ•Á}Í¥é”ôØÀ°4(€€€€€€€µ¥¹}Ý¥¹‘½ÝÌôÈ°4(€€€€¤4(4(€€€…ÍÍ•ÉÐ±•¸¡Ý¥¹‘½ÝÌ¤€ôô€ÜÔ4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍlÁt¹ÑÉ…¥¹}ÍÑ…ÉÑ}Ñ¥µ”€ôôÁ¹Q¥µ•ÍÑ…µÀ ˆÈÀÈÌ´ÀÄ´ÀÌ€ÀÀèÀÀèÀÀˆ¤4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍlÁt¹ÑÉ…¥¹}•¹‘}Ñ¥µ”€ôôÁ¹Q¥µ•ÍÑ…µÀ ˆÈÀÈÌ´ÀØ´ÈÜ€ÈÀèÀÀèÀÀˆ¤4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍlÁt¹Ñ•ÍÑ}ÍÑ…ÉÑ}Ñ¥µ”€ôôÁ¹Q¥µ•ÍÑ…µÀ ˆÈÀÈÌ´ÀØ´Èà€ÀÀèÀÀèÀÀˆ¤4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍlÁt¹Ñ•ÍÑ}•¹‘}Ñ¥µ”€ôôÁ¹Q¥µ•ÍÑ…µÀ ˆÈÀÈÌ´ÀÜ´ÈØ€ÄØèÀÀèÀÀˆ¤4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍl´Åt¹ÑÉ…¥¹}ÍÑ…ÉÐ€ôô€ÐÐÐÀ4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍl´Åt¹Ñ•ÍÑ}•¹€ôô€ÔÌÄÔ4(€€€…ÍÍ•ÉÐÝ¥¹‘½ÝÍl´Åt¹Ñ•ÍÑ}•¹‘}Ñ¥µ”€ôôÁ¹Q¥µ•ÍÑ…µÀ ˆÈÀÈØ´ÀØ´ÄÄ€ÄÈèÀÀèÀÀˆ¤4(4(4)‘•˜Ñ•ÍÑ}É•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ñ}¥¹½É•Í}ÉÕ¹Ñ¥µ•}™½ÉÝ…É‘}µ•Ñ…‘…Ñ„ ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}4ÄÕ|ÀÀÄˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰4ÄÔˆ°4(€€€€€€€€‰¥¹‘¥…Ñ½ÉÌˆèl‰•µ„ˆ°€‰…ÑÈ‰t°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÈ°€‰•µ…}Í±½Üˆè€ÈØ°€‰É¥Í­}Á•É•¹Ðˆè€À¸Õô°4(€€€€€€€€‰Í¥é¥¹œˆèì‰µ½‘”ˆè€‰É¥Í­}Á•É•¹Ðˆ°€‰É¥Í­}Á•É•¹Ðˆè€À¸Õô°4(€€€ô4(€€€™½ÉÝ…É‘}½¹™¥œ€ôì4(€€€€€€€€¨©Í…µÁ±•}½¹™¥œ°4(€€€€€€€€‰Í…µÁ±•}ÍÑÉ…Ñ•å}¥ˆè€‰Í…µÁ±•}4ÄÕ|ÀÀÄˆ°4(€€€€€€€€‰Í…µÁ±•}½¹™¥}Á…Ñ ˆèÍÑÈ¡I==P€¼€‰ÑµÀˆ€¼€‰½¹™¥œ¹Á­°ˆ¤°4(€€€€€€€€‰Í…µÁ±•}É…¹¬ˆè€Ä°4(€€€€€€€€‰A¡…Í”ˆè€‰aQ}==M}ˆ°4(€€€ô4(4(€€€…ÍÍ•ÉÐÉ•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ð¡Í…µÁ±•}½¹™¥œ¤€ôôÉ•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ð 4(€€€€€€€™½ÉÝ…É‘}½¹™¥œ4(€€€€¤4(€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä¡Í…µÁ±•}½¹™¥œ°™½ÉÝ…É‘}½¹™¥œ¤4(4(4)‘•˜Ñ•ÍÑ}…ÍÍ•ÉÑ}•áÁ•Ñ•‘}É•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ñ}…•ÁÑÍ}µ…Ñ¡¥¹}¡…Í  ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}µ…Ñ¡|ÀÀÄˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰4ÄÔˆ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÈ°€‰•µ…}Í±½Üˆè€ÈÙô°4(€€€ô4(€€€•áÁ•Ñ•€ôÉ•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ð¡Í…µÁ±•}½¹™¥œ¤4(4(€€€…ÍÍ•ÉÐ€ 4(€€€€€€€…ÍÍ•ÉÑ}•áÁ•Ñ•‘}É•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ð¡•áÁ•Ñ•°Í…µÁ±•}½¹™¥œ¤€ôô•áÁ•Ñ•4(€€€€¤4(4(4)‘•˜Ñ•ÍÑ}…ÍÍ•ÉÑ}•áÁ•Ñ•‘}É•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ñ}É•©•ÑÍ}µ¥ÍÍ¥¹}¡…Í  ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}µ¥ÍÍ¥¹}™Àˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰ Äˆ°4(€€€€€€€€‰Á…É…µÌˆèì‰ÉÈˆè€Ä¸Õô°4(€€€ô4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰É•ÅÕ¥É•ÌÑ¡”Í…µÁ±”µÍ•±•Ñ•ˆ¤è4(€€€€€€€…ÍÍ•ÉÑ}•áÁ•Ñ•‘}É•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ð ˆˆ°Í…µÁ±•}½¹™¥œ¤4(4(4)‘•˜Ñ•ÍÑ}…ÍÍ•ÉÑ}•áÁ•Ñ•‘}É•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ñ}É•©•ÑÍ}µÕÑ…Ñ•‘}½¹™¥œ ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}™Á|ÀÀÈˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰4ÌÀˆ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÈ°€‰•µ…}Í±½Üˆè€ÈØ°€‰É¥Í­}Á•É•¹Ðˆè€À¸Õô°4(€€€ô4(€€€µÕÑ…Ñ•€ôì4(€€€€€€€€¨©Í…µÁ±•}½¹™¥œ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÀ°€‰•µ…}Í±½Üˆè€ÈØ°€‰É¥Í­}Á•É•¹Ðˆè€À¸Õô°4(€€€ô4(€€€•áÁ•Ñ•€ôÉ•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ð¡Í…µÁ±•}½¹™¥œ¤4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰™¥¹•ÉÁÉ¥¹Ðµ¥Íµ…Ñ ˆ¤è4(€€€€€€€…ÍÍ•ÉÑ}•áÁ•Ñ•‘}É•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ð¡•áÁ•Ñ•°µÕÑ…Ñ•¤4(4(4)‘•˜Ñ•ÍÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñå}É•©•ÑÍ}É•Í•…É¡}Á…É…µ•Ñ•É}¡…¹•Ì ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•} Å|ÀÀÈˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰ Äˆ°4(€€€€€€€€‰¥¹‘¥…Ñ½ÉÌˆèl‰•µ„ˆ°€‰…ÑÈ‰t°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÈ°€‰•µ…}Í±½Üˆè€ÈØ°€‰É¥Í­}Á•É•¹Ðˆè€À¸Õô°4(€€€€€€€€‰•á¥ÑÌˆèì‰ÉÈˆè€Ä¸Áô°4(€€€ô4(€€€™½ÉÝ…É‘}½¹™¥œ€ôì4(€€€€€€€€¨©Í…µÁ±•}½¹™¥œ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÀ°€‰•µ…}Í±½Üˆè€ÈØ°€‰É¥Í­}Á•É•¹Ðˆè€À¸Õô°4(€€€€€€€€‰Í…µÁ±•}ÍÑÉ…Ñ•å}¥ˆè€‰Í…µÁ±•} Å|ÀÀÈˆ°4(€€€ô4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰á…Ð™½ÉÝ…É½¹™¥œµ¥Íµ…Ñ ˆ¤è4(€€€€€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä¡Í…µÁ±•}½¹™¥œ°™½ÉÝ…É‘}½¹™¥œ¤4(4(4)‘•˜Ñ•ÍÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñå}‘½•Í}¹½Ñ}¥¹½É•}¹•ÍÑ•‘}É•Í•…É¡}Á…É…µÌ ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}4ÌÁ|ÀÀÌˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰4ÌÀˆ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÈ°€‰Ý¥¹‘½Ý}¥ˆè€Õô°4(€€€€€€€€‰™¥±Ñ•ÉÌˆèì‰Í•ÍÍ¥½¸ˆèì‰Ý¥¹‘½Ý}¥ˆè€‰±½¹‘½¹}½Á•¸‰õô°4(€€€ô4(€€€™½ÉÝ…É‘}½¹™¥œ€ôì4(€€€€€€€€¨©Í…µÁ±•}½¹™¥œ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÈ°€‰Ý¥¹‘½Ý}¥ˆè€Ùô°4(€€€ô4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰á…Ð™½ÉÝ…É½¹™¥œµ¥Íµ…Ñ ˆ¤è4(€€€€€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä¡Í…µÁ±•}½¹™¥œ°™½ÉÝ…É‘}½¹™¥œ¤4(4(4)‘•˜Ñ•ÍÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñå}ÑÉ•…ÑÍ}Ñ½Á}±•Ù•±}Ý¥¹‘½Ý}¥‘}…Í}É•Í•…É¡}‘…Ñ„ ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}4ÌÁ}Ý¥¹‘½Üˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰4ÌÀˆ°4(€€€€€€€€‰Ý¥¹‘½Ý}¥ˆè€Ô°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÉô°4(€€€ô4(€€€™½ÉÝ…É‘}½¹™¥œ€ôì4(€€€€€€€€¨©Í…µÁ±•}½¹™¥œ°4(€€€€€€€€‰Ý¥¹‘½Ý}¥ˆè€Ø°4(€€€ô4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰á…Ð™½ÉÝ…É½¹™¥œµ¥Íµ…Ñ ˆ¤è4(€€€€€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä¡Í…µÁ±•}½¹™¥œ°™½ÉÝ…É‘}½¹™¥œ¤4(4(4)‘•˜Ñ•ÍÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñå}…±±½ÝÍ}•áÁ±¥¥Ñ}¹•ÍÑ•‘}µ•Ñ…‘…Ñ…}•á•µÁÑ¥½¹Ì ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}4ÌÁ|ÀÀÐˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰4ÌÀˆ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÈ°€‰Ý¥¹‘½Ý}¥ˆè€Õô°4(€€€€€€€€‰ÉÕ¹Ñ¥µ•}µ•Ñ…‘…Ñ„ˆèì‰±½…‘•‘}Ý¥¹‘½Ý}¥ˆè€‰±½¹‘½¹}½Á•¸‰ô°4(€€€ô4(€€€™½ÉÝ…É‘}½¹™¥œ€ôì4(€€€€€€€€¨©Í…µÁ±•}½¹™¥œ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÈ°€‰Ý¥¹‘½Ý}¥ˆè€Õô°4(€€€€€€€€‰ÉÕ¹Ñ¥µ•}µ•Ñ…‘…Ñ„ˆèì‰±½…‘•‘}Ý¥¹‘½Ý}¥ˆè€‰¹•Ý}ÉÕ¹Ñ¥µ•}Ý¥¹‘½Ü‰ô°4(€€€ô4(4(€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä 4(€€€€€€€Í…µÁ±•}½¹™¥œ°4(€€€€€€€™½ÉÝ…É‘}½¹™¥œ°4(€€€€€€€¥¹½É•‘}Á…Ñ¡Ìõì ‰ÉÕ¹Ñ¥µ•}µ•Ñ…‘…Ñ„ˆ°€‰±½…‘•‘}Ý¥¹‘½Ý}¥ˆ¥ô°4(€€€€¤4(4(4)‘•˜Ñ•ÍÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñå}É•©•ÑÍ}ÍÑÉÕÑÕÉ•‘}µ•Ñ…‘…Ñ…}•á•µÁÑ¥½¹Ì ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}4ÌÁ|ÀÀÐˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰4ÌÀˆ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÈ°€‰Ý¥¹‘½Ý}¥ˆè€Õô°4(€€€€€€€€‰ÉÕ¹Ñ¥µ•}µ•Ñ…‘…Ñ„ˆèì4(€€€€€€€€€€€€‰±½…‘•‘}Ý¥¹‘½Üˆèì‰¥ˆè€‰±½¹‘½¹}½Á•¸ˆ°€‰•µ…}™…ÍÐˆè€ÄÉô°4(€€€€€€€ô°4(€€€ô4(€€€™½ÉÝ…É‘}½¹™¥œ€ôì4(€€€€€€€€¨©Í…µÁ±•}½¹™¥œ°4(€€€€€€€€‰ÉÕ¹Ñ¥µ•}µ•Ñ…‘…Ñ„ˆèì4(€€€€€€€€€€€€‰±½…‘•‘}Ý¥¹‘½Üˆèì‰¥ˆè€‰¹•Ý}ÉÕ¹Ñ¥µ•}Ý¥¹‘½Üˆ°€‰•µ…}™…ÍÐˆè€ÄÁô°4(€€€€€€€ô°4(€€€ô4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì 4(€€€€€€€U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰µÕÍÐÁ½¥¹ÐÑ¼Í…±…È±•…˜Ù…±Õ•Ìˆ4(€€€€¤è4(€€€€€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä 4(€€€€€€€€€€€Í…µÁ±•}½¹™¥œ°4(€€€€€€€€€€€™½ÉÝ…É‘}½¹™¥œ°4(€€€€€€€€€€€¥¹½É•‘}Á…Ñ¡Ìõì ‰ÉÕ¹Ñ¥µ•}µ•Ñ…‘…Ñ„ˆ°€‰±½…‘•‘}Ý¥¹‘½Üˆ¥ô°4(€€€€€€€€¤4(4(4)‘•˜Ñ•ÍÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñå}É•©•ÑÍ}‰É½…‘}µ•Ñ…‘…Ñ…}É½½Ñ}•á•µÁÑ¥½¹Ì ¤è4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰Ñ…É•ÐÍÁ•¥™¥Œµ•Ñ…‘…Ñ„™¥•±‘Ìˆ¤è4(€€€€€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä 4(€€€€€€€€€€€ì‰ÉÕ¹Ñ¥µ•}µ•Ñ…‘…Ñ„ˆèì‰±½…‘•‘}Ý¥¹‘½Ý}¥ˆè€‰„‰õô°4(€€€€€€€€€€€ì‰ÉÕ¹Ñ¥µ•}µ•Ñ…‘…Ñ„ˆèì‰±½…‘•‘}Ý¥¹‘½Ý}¥ˆè€‰ˆ‰õô°4(€€€€€€€€€€€¥¹½É•‘}Á…Ñ¡Ìõì ‰ÉÕ¹Ñ¥µ•}µ•Ñ…‘…Ñ„ˆ°¥ô°4(€€€€€€€€¤4(4(4)‘•˜Ñ•ÍÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñå}É•©•ÑÍ}¹•ÍÑ•‘}•á•µÁÑ¥½¹Í}™½É}É•Í•…É¡}Á…Ñ¡Ì ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}4ÌÁ|ÀÀÐˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰4ÌÀˆ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÈ°€‰Ý¥¹‘½Ý}¥ˆè€Õô°4(€€€ô4(€€€™½ÉÝ…É‘}½¹™¥œ€ôì4(€€€€€€€€¨©Í…µÁ±•}½¹™¥œ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÀ°€‰Ý¥¹‘½Ý}¥ˆè€Õô°4(€€€ô4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì 4(€€€€€€€U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰¹•ÍÑ•¥¹½É•Ì…É”É•ÍÑÉ¥Ñ•Ñ¼…Õ‘¥Ñ•ÉÕ¹Ñ¥µ”µ•Ñ…‘…Ñ„É½½ÑÌˆ4(€€€€¤è4(€€€€€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä 4(€€€€€€€€€€€Í…µÁ±•}½¹™¥œ°4(€€€€€€€€€€€™½ÉÝ…É‘}½¹™¥œ°4(€€€€€€€€€€€¥¹½É•‘}Á…Ñ¡Ìõì ‰Á…É…µÌˆ°€‰•µ…}™…ÍÐˆ¥ô°4(€€€€€€€€¤4(4(4)‘•˜Ñ•ÍÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñå}É•©•ÑÍ}Ñ½Á}±•Ù•±}É•Í•…É¡}­•å}•á•µÁÑ¥½¹Ì ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}4ÌÁ|ÀÀÐˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰4ÌÀˆ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÉô°4(€€€ô4(€€€™½ÉÝ…É‘}½¹™¥œ€ôì4(€€€€€€€€¨©Í…µÁ±•}½¹™¥œ°4(€€€€€€€€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÁô°4(€€€ô4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì 4(€€€€€€€U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰…Õ‘¥Ñ•Ñ½Àµ±•Ù•°ÉÕ¹Ñ¥µ”µ•Ñ…‘…Ñ„ˆ4(€€€€¤è4(€€€€€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä 4(€€€€€€€€€€€Í…µÁ±•}½¹™¥œ°4(€€€€€€€€€€€™½ÉÝ…É‘}½¹™¥œ°4(€€€€€€€€€€€¥¹½É•‘}­•åÌõì‰Á…É…µÌ‰ô°4(€€€€€€€€¤4(4(4)‘•˜Ñ•ÍÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñå}¥¹½É•Í}É•½É‘•‘}™¥¹•ÉÁÉ¥¹Ñ}µ•Ñ…‘…Ñ„ ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì‰¥ˆè€‰Í…µÁ±•}4ÄÕ|ÀÀÔˆ°€‰Ñ¥µ•™É…µ”ˆè€‰4ÄÔˆ°€‰Á…É…µÌˆèì‰•µ…}™…ÍÐˆè€ÄÉõô4(€€€™½ÉÝ…É‘}½¹™¥œ€ôì4(€€€€€€€€¨©Í…µÁ±•}½¹™¥œ°4(€€€€€€€€‰Í…µÁ±•}ÍÑÉ…Ñ•å}¥ˆè€‰Í…µÁ±•}4ÄÕ|ÀÀÔˆ°4(€€€€€€€€‰Í…µÁ±•}½¹™¥}™¥¹•ÉÁÉ¥¹Ðˆè€‰Í¡„ÈÔØéÁ±…•¡½±‘•Èˆ°4(€€€ô4(4(€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä¡Í…µÁ±•}½¹™¥œ°™½ÉÝ…É‘}½¹™¥œ¤4(4(4)‘•˜Ñ•ÍÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñå}É•©•ÑÍ}¹½¹}™¥¹¥Ñ•}Ù…±Õ•Ì ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì‰¥ˆè€‰Í…µÁ±•} Ñ|ÀÀÌˆ°€‰Ñ¥µ•™É…µ”ˆè€‰ Ðˆ°€‰Á…É…µÌˆèì‰ÉÈˆè€Ä¸Áõô4(€€€™½ÉÝ…É‘}½¹™¥œ€ôì‰¥ˆè€‰Í…µÁ±•} Ñ|ÀÀÌˆ°€‰Ñ¥µ•™É…µ”ˆè€‰ Ðˆ°€‰Á…É…µÌˆèì‰ÉÈˆè™±½…Ð ‰¹…¸ˆ¥õô4(4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰¹½¸µ™¥¹¥Ñ”ˆ¤è4(€€€€€€€É•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ð¡™½ÉÝ…É‘}½¹™¥œ¤4(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡U¹Í…™•Ù…±Õ…Ñ¥½¹ÉÉ½È°µ…Ñ ô‰¹½¸µ™¥¹¥Ñ”ˆ¤è4(€€€€€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä¡Í…µÁ±•}½¹™¥œ°™½ÉÝ…É‘}½¹™¥œ¤4(4(4)‘•˜Ñ•ÍÑ}É•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ñ}¹½Éµ…±¥é•Í}¹ÕµÁå}Í…±…É}Ù…±Õ•Ì ¤è4(€€€Í…µÁ±•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}¹Á|ÀÀÄˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰ Äˆ°4(€€€€€€€€‰Á…É…µÌˆèì4(€€€€€€€€€€€€‰•µ…}™…ÍÐˆè¹À¹¥¹ÐØÐ ÄÈ¤°4(€€€€€€€€€€€€‰É¥Í­}Á•É•¹Ðˆè¹À¹™±½…ÐØÐ À¸Ô¤°4(€€€€€€€€€€€€‰•¹…‰±•ˆè¹À¹‰½½±|¡QÉÕ”¤°4(€€€€€€€ô°4(€€€ô4(€€€¹…Ñ¥Ù•}½¹™¥œ€ôì4(€€€€€€€€‰¥ˆè€‰Í…µÁ±•}¹Á|ÀÀÄˆ°4(€€€€€€€€‰Ñ¥µ•™É…µ”ˆè€‰ Äˆ°4(€€€€€€€€‰Á…É…µÌˆèì4(€€€€€€€€€€€€‰•µ…}™…ÍÐˆè€ÄÈ°4(€€€€€€€€€€€€‰É¥Í­}Á•É•¹Ðˆè€À¸Ô°4(€€€€€€€€€€€€‰•¹…‰±•ˆèQÉÕ”°4(€€€€€€€ô°4(€€€ô4(4(€€€…ÍÍ•ÉÐÉ•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ð¡Í…µÁ±•}½¹™¥œ¤€ôôÉ•Í•…É¡}½¹™¥}™¥¹•ÉÁÉ¥¹Ð 4(€€€€€€€¹…Ñ¥Ù•}½¹™¥œ4(€€€€¤4(€€€…ÍÍ•ÉÑ}•á…Ñ}™½ÉÝ…É‘}½¹™¥}¥‘•¹Ñ¥Ñä¡Í…µÁ±•}½¹™¥œ°¹…Ñ¥Ù•}½¹™¥œ¤4(