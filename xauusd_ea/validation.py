"""Leakage and identity guards for audited sample/forward evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_SAMPLE_RATIO_MIN = 0.50
DEFAULT_SAMPLE_RATIO_MAX = 0.90
DEFAULT_CONFIG_IDENTITY_IGNORED_TOP_LEVEL_KEYS = frozenset(
    {
        "Exact Config Forward Test",
        "Loaded Config Path",
        "Phase",
        "equity_curve",
        "final_capital",
        "metrics",
        "sample_config_path",
        "sample_rank",
        "sample_strategy_id",
        "trades",
    }
)


class UnsafeEvaluationError(ValueError):
    """Raised when a leakage-safe evaluation cannot be performed."""


@dataclass(frozen=True)
class SampleHoldoutSplit:
    timeframe: str
    sample_ratio: float
    split_index: int
    sample: pd.DataFrame
    holdout: pd.DataFrame

    @property
    def sample_start(self) -> pd.Timestamp:
        return pd.Timestamp(self.sample.index[0])

    @property
    def sample_end(self) -> pd.Timestamp:
        return pd.Timestamp(self.sample.index[-1])

    @property
    def holdout_start(self) -> pd.Timestamp:
        return pd.Timestamp(self.holdout.index[0])

    @property
    def holdout_end(self) -> pd.Timestamp:
        return pd.Timestamp(self.holdout.index[-1])


@dataclass(frozen=True)
class WalkForwardWindow:
    timeframe: str
    window: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    train_start_time: pd.Timestamp
    train_end_time: pd.Timestamp
    test_start_time: pd.Timestamp
    test_end_time: pd.Timestamp


def _require_chronological_datetime_index(
    df: pd.DataFrame, *, context: str
) -> None:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise UnsafeEvaluationError(f"{context} requires a DatetimeIndex")
    if not df.index.is_monotonic_increasing:
        raise UnsafeEvaluationError(f"{context} requires sorted timestamps")
    if not df.index.is_unique:
        raise UnsafeEvaluationError(
            f"{context} requires unique timestamps without overlap"
        )


def split_sample_holdout(
    df: pd.DataFrame,
    *,
    timeframe: str,
    sample_ratio: float,
    min_sample_rows: int = 1,
    min_holdout_rows: int = 1,
) -> SampleHoldoutSplit:
    """Chronologically split one timeframe into sample and holdout segments.

    This helper never clips invalid ratios and never falls back to full-sample
    evaluation. If a safe split cannot be produced, it raises explicitly so the
    caller can fail or skip the candidate.
    """
    _require_chronological_datetime_index(df, context="Sample/holdout split")
    if min_sample_rows < 1 or min_holdout_rows < 1:
        raise ValueError("Minimum sample and holdout rows must be positive")

    ratio = float(sample_ratio)
    if not DEFAULT_SAMPLE_RATIO_MIN <= ratio <= DEFAULT_SAMPLE_RATIO_MAX:
        raise UnsafeEvaluationError(
            "Sample ratio must stay inside the audited range "
            f"[{DEFAULT_SAMPLE_RATIO_MIN:.2f}, {DEFAULT_SAMPLE_RATIO_MAX:.2f}]"
        )

    total_rows = len(df)
    min_total_rows = min_sample_rows + min_holdout_rows
    if total_rows < min_total_rows:
        raise UnsafeEvaluationError(
            f"{timeframe}: not enough rows for a safe split; need at least "
            f"{min_total_rows}, found {total_rows}"
        )

    split_index = int(total_rows * ratio)
    if split_index < min_sample_rows or total_rows - split_index < min_holdout_rows:
        raise UnsafeEvaluationError(
            f"{timeframe}: sample_ratio={ratio:.2f} cannot satisfy the required "
            f"minimum rows without changing the audited boundary; requested split "
            f"yields sample={split_index} and holdout={total_rows - split_index}, "
            f"required at least {min_sample_rows}/{min_holdout_rows}"
        )
    sample = df.iloc[:split_index].copy()
    holdout = df.iloc[split_index:].copy()

    if len(sample) < min_sample_rows or len(holdout) < min_holdout_rows:
        raise UnsafeEvaluationError(
            f"{timeframe}: split produced sample={len(sample)} and "
            f"holdout={len(holdout)} rows; required at least "
            f"{min_sample_rows}/{min_holdout_rows}"
        )
    if pd.Timestamp(sample.index[-1]) >= pd.Timestamp(holdout.index[0]):
        raise UnsafeEvaluationError(
            f"{timeframe}: sample/holdout overlap detected at "
            f"{sample.index[-1]} and {holdout.index[0]}"
        )

    return SampleHoldoutSplit(
        timeframe=str(timeframe),
        sample_ratio=ratio,
        split_index=split_index,
        sample=sample,
        holdout=holdout,
    )


def plan_walk_forward_windows(
    df: pd.DataFrame,
    *,
    timeframe: str,
    train_window: int,
    test_window: int,
    step_size: int,
    min_windows: int = 1,
) -> list[WalkForwardWindow]:
    """Plan chronological walk-forward windows without fallback behavior."""
    _require_chronological_datetime_index(df, context="Walk-forward planning")
    if train_window < 1 or test_window < 1 or step_size < 1:
        raise ValueError("train_window, test_window, and step_size must be positive")
    if min_windows < 1:
        raise ValueError("min_windows must be positive")

    total_rows = len(df)
    required_rows = train_window + test_window
    if total_rows < required_rows:
        raise UnsafeEvaluationError(
            f"{timeframe}: not enough rows for walk-forward planning; need at least "
            f"{required_rows}, found {total_rows}"
        )

    windows: list[WalkForwardWindow] = []
    window_number = 1
    train_start = 0
    while train_start + required_rows <= total_rows:
        train_end = train_start + train_window
        test_start = train_end
        test_end = test_start + test_window
        windows.append(
            WalkForwardWindow(
                timeframe=str(timeframe),
                window=window_number,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_start_time=pd.Timestamp(df.index[train_start]),
                train_end_time=pd.Timestamp(df.index[train_end - 1]),
                test_start_time=pd.Timestamp(df.index[test_start]),
                test_end_time=pd.Timestamp(df.index[test_end - 1]),
            )
        )
        window_number += 1
        train_start += step_size

    if len(windows) < min_windows:
        raise UnsafeEvaluationError(
            f"{timeframe}: walk-forward planning produced {len(windows)} windows; "
            f"required at least {min_windows}"
        )
    return windows


def research_config_payload(
    config: dict[str, Any],
    *,
    ignored_keys: set[str] | frozenset[str] | None = None,
    ignored_paths: set[tuple[str, ...]] | frozenset[tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    """Return a canonical config payload suitable for identity hashing."""
    active_ignored_keys = (
        DEFAULT_CONFIG_IDENTITY_IGNORED_TOP_LEVEL_KEYS
        if ignored_keys is None
        else frozenset(ignored_keys)
    )
    active_ignored_paths = frozenset() if ignored_paths is None else frozenset(ignored_paths)
    return _normalize_value(
        config,
        ignored_keys=active_ignored_keys,
        ignored_paths=active_ignored_paths,
    )


def research_config_fingerprint(
    config: dict[str, Any],
    *,
    ignored_keys: set[str] | frozenset[str] | None = None,
    ignored_paths: set[tuple[str, ...]] | frozenset[tuple[str, ...]] | None = None,
) -> str:
    payload = research_config_payload(
        config,
        ignored_keys=ignored_keys,
        ignored_paths=ignored_paths,
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def assert_exact_forward_config_identity(
    sample_config: dict[str, Any],
    forward_config: dict[str, Any],
    *,
    ignored_keys: set[str] | frozenset[str] | None = None,
    ignored_paths: set[tuple[str, ...]] | frozenset[tuple[str, ...]] | None = None,
) -> str:
    """Ensure forward evaluation uses the exact same research config."""
    sample_payload = research_config_payload(
        sample_config,
        ignored_keys=ignored_keys,
        ignored_paths=ignored_paths,
    )
    forward_payload = research_config_payload(
        forward_config,
        ignored_keys=ignored_keys,
        ignored_paths=ignored_paths,
    )
    if sample_payload != forward_payload:
        raise UnsafeEvaluationError(
            "Exact forward config mismatch; evaluation must use the identical "
            "sample-selected config without research-parameter changes"
        )
    return research_config_fingerprint(
        sample_config,
        ignored_keys=ignored_keys,
        ignored_paths=ignored_paths,
    )


def _normalize_value(
    value: Any,
    *,
    ignored_keys: frozenset[str],
    ignored_paths: frozenset[tuple[str, ...]],
    path: tuple[str, ...] = (),
) -> dict[str, Any] | list[Any] | str | int | float | bool | None:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value, key=lambda item: str(item)):
            key_text = str(key)
            key_path = path + (key_text,)
            if (not path and key_text in ignored_keys) or key_path in ignored_paths:
                continue
            normalized[key_text] = _normalize_value(
                value[key],
                ignored_keys=ignored_keys,
                ignored_paths=ignored_paths,
                path=key_path,
            )
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _normalize_value(
                item,
                ignored_keys=ignored_keys,
                ignored_paths=ignored_paths,
                path=path,
            )
            for item in value
        ]
    if isinstance(value, set):
        return sorted(
            _normalize_value(
                item,
                ignored_keys=ignored_keys,
                ignored_paths=ignored_paths,
                path=path,
            )
            for item in value
        )
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _normalize_value(
            value.item(),
            ignored_keys=ignored_keys,
            ignored_paths=ignored_paths,
            path=path,
        )
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnsafeEvaluationError(
                "Exact forward config contains a non-finite numeric value"
            )
        return value
    raise UnsafeEvaluationError(
        f"Unsupported config value type for identity hashing: {type(value)!r}"
    )
