"""Deterministic indicator math used by the active research engine."""

from __future__ import annotations

import math

import pandas as pd


def _close_series(close: pd.Series) -> pd.Series:
    series = pd.Series(close, index=close.index, dtype=float)
    if series.empty:
        raise ValueError("close must contain at least one value")
    return series


def macd(
    close: pd.Series,
    fast: int,
    slow: int,
    signal: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return MACD line, signal, and histogram for one frozen parameter set."""
    fast = int(fast)
    slow = int(slow)
    signal = int(signal)
    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError("MACD periods must be positive")
    if fast >= slow:
        raise ValueError("MACD fast period must be less than slow period")

    close_series = _close_series(close)
    fast_ema = close_series.ewm(span=fast, adjust=False).mean()
    slow_ema = close_series.ewm(span=slow, adjust=False).mean()
    line = fast_ema - slow_ema
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return line, signal_line, line - signal_line


def bollinger_bands(
    close: pd.Series,
    period: int,
    multiplier: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return middle, upper, and lower population-standard-deviation bands."""
    period = int(period)
    multiplier = float(multiplier)
    if period <= 1:
        raise ValueError("Bollinger period must be greater than one")
    if not math.isfinite(multiplier) or multiplier <= 0.0:
        raise ValueError("Bollinger multiplier must be finite and positive")

    close_series = _close_series(close)
    middle = close_series.rolling(period).mean()
    deviation = close_series.rolling(period).std(ddof=0)
    return middle, middle + multiplier * deviation, middle - multiplier * deviation
