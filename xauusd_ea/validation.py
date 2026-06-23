"""Leakage and identity guards for audited sample/forward evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
from typing import Any

import pandas as pd

DEFAULT_SAMPLE_RATIO_MIN = 0.50
DEFAULT_SAMPLE_RATIO_MAX = 0.90
DEFAULT_CONFIG_IDENTITY_IGNORED_KEYS = frozenset(
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
        "window_id",
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
    if not isinstance(df.index, pd.DatetimeIndex):
        raise UnsafeEvaluationError("Sample/holdout split requires a DatetimeIndex")
    if not df.index.is_monotonic_increasing:
        raise UnsafeEvaluationError("Sample/holdout split requires sorted timestamps")
    if not df.index.is_unique:
        raise UnsafeEvaluationError(
            "Sample/holdout split requires unique timestamps without overlap"
        )
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
    split_index = max(min_sample_rows, min(split_index, total_rows - min_holdout_rows))
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


def research_config_payload(
    config: dict[str, Any], *, ignored_keys: set[str] | frozenset[str] | None = None
) -> dict[str, Any]:
    """Return a canonical config payload suitable for identity hashing."""
    active_ignored_keys = (
        DEFAULT_CONFIG_IDENTITY_IGNORED_KEYS
        if ignored_keys is None
        else frozenset(ignored_keys)
    )
    return _normalize_value(config, ignored_keys=active_ignored_keys)


def research_config_fingerprint(
    config: dict[str, Any], *, ignored_keys: set[str] | frozenset[str] | None = None
) -> str:
    payload = research_config_payload(config, ignored_keys=ignored_keys)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def assert_exact_forward_config_identity(
    sample_config: dict[str, Any],
    forward_config: dict[str, Any],
    *,
    ignored_keys: set[str] | frozenset[str] | None = None,
) -> str:
    """Ensure forward evaluation uses the exact same research config."""
    sample_payload = research_config_payload(sample_config, ignored_keys=ignored_keys)
    forward_payload = research_config_payload(forward_config, ignored_keys=ignored_keys)
    if sample_payload != forward_payload:
        raise UnsafeEvaluationError(
            "Exact forward config mismatch; evaluation must use the identical "
            "sample-selected config without research-parameter changes"
        )
    return research_config_fingerprint(sample_config, ignored_keys=ignored_keys)


def _normalize_value(
    value: Any, *, ignored_keys: frozenset[str]
) -> dict[str, Any] | list[Any] | str | int | float | bool | None:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if key in ignored_keys:
                continue
            normalized[str(key)] = _normalize_value(value[key], ignored_keys=ignored_keys)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item, ignored_keys=ignored_keys) for item in value]
    if isinstance(value, set):
        return sorted(_normalize_value(item, ignored_keys=ignored_keys) for item in value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
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
