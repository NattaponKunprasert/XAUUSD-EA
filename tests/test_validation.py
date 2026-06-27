from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from xauusd_ea.validation import (
    SampleHoldoutSplit,
    UnsafeEvaluationError,
    assert_exact_forward_config_identity,
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
