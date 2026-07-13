"""Deterministic, closed-bar exit helpers for the research engine."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from .baseline import require_runtime_broker_spec
from .execution import spread_price, to_price_units


SUPPORTED_FIBONACCI_EXTENSIONS = (1.618, 2.0, 2.618)


def resolve_intrabar_stop_target(
    open_position: Mapping[str, Any],
    bar_open_bid: float,
    bar_high_bid: float,
    bar_low_bid: float,
    friction: Mapping[str, Any] | None,
    runtime_spec: Mapping[str, Any],
) -> tuple[float | None, str | None]:
    """Resolve one Bid-OHLC bar under the conservative SL/TP policy.

    Long exits trigger directly on Bid. Short exits trigger on Ask values
    derived from the verified Bid source and audited spread, while the raw Bid
    price is returned for the execution layer. Gap-through opens execute at the
    opening Bid; when both levels are touched later in one bar, the stop wins.
    """
    spec = require_runtime_broker_spec(runtime_spec)
    if not isinstance(open_position, Mapping):
        raise ValueError("open_position must be a mapping")
    missing = [
        field
        for field in ("direction", "stop_loss", "take_profit")
        if field not in open_position
    ]
    if missing:
        raise ValueError(f"open_position is missing required fields: {missing!r}")

    bar_open = float(bar_open_bid)
    bar_high = float(bar_high_bid)
    bar_low = float(bar_low_bid)
    stop = float(open_position["stop_loss"])
    target = float(open_position["take_profit"])
    if not all(
        math.isfinite(value)
        for value in (bar_open, bar_high, bar_low, stop, target)
    ):
        raise ValueError("bar prices, stop_loss, and take_profit must be finite")
    if bar_low > bar_open or bar_open > bar_high:
        raise ValueError("Bid OHLC must satisfy low <= open <= high")

    direction = str(open_position["direction"]).lower()
    stop_reason = "TrailingStop" if open_position.get("stop_loss_is_trailing") else "SL"
    if direction == "long":
        if stop >= target:
            raise ValueError("long stop_loss must be below take_profit")
        if bar_open <= stop:
            return bar_open, stop_reason
        if bar_open >= target:
            return bar_open, "TP"
        if bar_low <= stop:
            return stop, stop_reason
        if bar_high >= target:
            return target, "TP"
        return None, None

    if direction == "short":
        if stop <= target:
            raise ValueError("short stop_loss must be above take_profit")
        spread = spread_price(friction, spec)
        open_ask = bar_open + spread
        high_ask = bar_high + spread
        low_ask = bar_low + spread
        if open_ask >= stop:
            return bar_open, stop_reason
        if open_ask <= target:
            return bar_open, "TP"
        if high_ask >= stop:
            return float(stop - spread), stop_reason
        if low_ask <= target:
            return float(target - spread), "TP"
        return None, None

    raise ValueError("direction must be 'long' or 'short'")


def max_holding_exit_due(
    entry_index: int,
    current_index: int,
    max_holding_bars: int,
) -> bool:
    """Return whether a position has reached its configured bar limit.

    The entry bar has zero completed holding bars. A positive limit becomes
    due exactly when ``current_index - entry_index`` reaches that limit;
    non-positive limits disable the time exit.
    """
    if isinstance(entry_index, bool) or not isinstance(entry_index, int):
        raise ValueError("entry_index must be an integer")
    if isinstance(current_index, bool) or not isinstance(current_index, int):
        raise ValueError("current_index must be an integer")
    if isinstance(max_holding_bars, bool) or not isinstance(max_holding_bars, int):
        raise ValueError("max_holding_bars must be an integer")
    if entry_index < 0 or current_index < entry_index:
        raise ValueError("current_index must be at or after a non-negative entry_index")
    if max_holding_bars <= 0:
        return False
    return current_index - entry_index >= max_holding_bars


def next_trailing_stop(
    entry_price: float,
    current_stop: float,
    current_price: float,
    direction: str,
    trail_type: str,
    config: Mapping[str, Any] | None,
    runtime_spec: Mapping[str, Any],
    *,
    current_atr: float | None = None,
) -> float | None:
    """Return an improved close-bar trailing stop, or ``None`` if unchanged.

    ATR and percent trails follow the current fully closed bar. Step trails
    advance from the frozen entry price in verified broker points. The caller
    applies the returned stop only to later bars, so this helper cannot alter
    the intrabar decision for the bar that produced ``current_price``.
    """
    spec = require_runtime_broker_spec(runtime_spec)
    normalized_direction = str(direction).lower()
    if normalized_direction not in {"long", "short"}:
        raise ValueError("direction must be 'long' or 'short'")

    normalized_type = str(trail_type or "none").lower()
    if normalized_type == "none":
        return None
    if normalized_type not in {"atr", "percent", "step"}:
        raise ValueError("trail_type must be 'none', 'atr', 'percent', or 'step'")

    numeric_entry = float(entry_price)
    numeric_stop = float(current_stop)
    numeric_price = float(current_price)
    if not all(
        math.isfinite(value)
        for value in (numeric_entry, numeric_stop, numeric_price)
    ):
        raise ValueError("entry_price, current_stop, and current_price must be finite")

    cfg = dict(config or {})
    if normalized_type == "atr":
        if current_atr is None:
            return None
        numeric_atr = float(current_atr)
        multiplier = float(cfg.get("trail_multiplier", 1.5))
        if not math.isfinite(numeric_atr) or numeric_atr <= 0.0:
            raise ValueError("current_atr must be finite and positive")
        if not math.isfinite(multiplier) or multiplier <= 0.0:
            raise ValueError("trail_multiplier must be finite and positive")
        distance = numeric_atr * multiplier
        candidate = (
            numeric_price - distance
            if normalized_direction == "long"
            else numeric_price + distance
        )
    elif normalized_type == "percent":
        percent = float(cfg.get("trail_percent", 0.5))
        if not math.isfinite(percent) or percent <= 0.0:
            raise ValueError("trail_percent must be finite and positive")
        distance = numeric_price * percent / 100.0
        candidate = (
            numeric_price - distance
            if normalized_direction == "long"
            else numeric_price + distance
        )
    else:
        step_points = float(cfg.get("trail_step_pips", 50.0))
        if not math.isfinite(step_points) or step_points <= 0.0:
            raise ValueError("trail_step_pips must be finite and positive")
        step_price = to_price_units(
            step_points,
            spec,
            {"cost_value_mode": "points"},
        )
        minimum_step = max(step_price, float(spec["point"]))
        favourable = (
            numeric_price - numeric_entry
            if normalized_direction == "long"
            else numeric_entry - numeric_price
        )
        steps = math.floor(max(0.0, favourable) / minimum_step)
        if steps <= 0:
            return None
        candidate = (
            numeric_entry + (steps - 1) * step_price
            if normalized_direction == "long"
            else numeric_entry - (steps - 1) * step_price
        )

    improved = (
        candidate > numeric_stop
        if normalized_direction == "long"
        else candidate < numeric_stop
    )
    return float(candidate) if improved else None


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
