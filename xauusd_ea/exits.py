"""Deterministic, closed-bar exit helpers for the research engine."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


SUPPORTED_FIBONACCI_EXTENSIONS = (1.618, 2.0, 2.618)


def fibonacci_extension_target(
    entry_price: float,
    df: pd.DataFrame,
    signal_index: int,
    direction: str,
    fib_levels: Iterable[float],
    *,
    lookback: int = 20,
) -> float:
    """Return the furthest configured target from closed-bar swing range.

    ``signal_index`` is the closed signal bar. The calculation includes that
    bar and never reads later rows, so a next-bar entry cannot leak future
    OHLC data into its target.
    """
    if direction not in {"long", "short"}:
        raise ValueError("direction must be 'long' or 'short'")
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if not {"high", "low"}.issubset(df.columns):
        raise ValueError("df must contain high and low columns")
    if not 0 <= signal_index < len(df):
        raise IndexError("signal_index is outside df")

    normalized_levels = []
    for raw_level in fib_levels:
        level = float(raw_level)
        if level > 10.0:
            level /= 100.0
        if not np.isfinite(level) or level not in SUPPORTED_FIBONACCI_EXTENSIONS:
            raise ValueError(
                f"unsupported Fibonacci extension {raw_level!r}; expected one of "
                f"{SUPPORTED_FIBONACCI_EXTENSIONS!r}"
            )
        normalized_levels.append(level)
    if not normalized_levels:
        raise ValueError("fib_levels must contain at least one extension")

    start = max(0, signal_index - lookback + 1)
    closed_window = df.iloc[start : signal_index + 1]
    swing_high = float(closed_window["high"].max())
    swing_low = float(closed_window["low"].min())
    swing_range = swing_high - swing_low
    if not np.isfinite(swing_range) or swing_range <= 0.0:
        raise ValueError("closed-bar Fibonacci swing range must be positive")

    distance = swing_range * max(normalized_levels)
    entry_price = float(entry_price)
    if not np.isfinite(entry_price):
        raise ValueError("entry_price must be finite")
    return entry_price + distance if direction == "long" else entry_price - distance
