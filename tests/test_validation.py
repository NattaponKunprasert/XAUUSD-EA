from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from xauusd_ea.baseline import load_mt5_csv
from xauusd_ea.validation import (
    SampleHoldoutSplit,
    UnsafeEvaluationError,
    WalkForwardWindow,
    assert_exact_forward_config_identity,
    plan_walk_forward_windows,
    research_config_fingerprint,
    split_sample_holdout,
)

ROOT = Path(__file__).resolve().parents[1]


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
        "filters": {"session": {"window_id": "london_open"}},
    }
    forward_config = {
        **sample_config,
        "params": {"ema_fast": 12, "window_id": 5},
        "filters": {"session": {"window_id": "new_runtime_window"}},
    }

    assert_exact_forward_config_identity(
        sample_config,
        forward_config,
        ignored_paths={("filters", "session", "window_id")},
    )


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
