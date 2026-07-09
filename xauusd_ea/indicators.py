"""Deterministic indicator math used by the active research engine."""

from __future__ import annotations

import math

import pandas as pd


def _close_series(close: pd.Series) -> pd.Series:
    series = pd.Series(close, index=close.index, dtype=float)
    if series.empty:
        raise ValueError("close must contain at least one value")
    return series


def exponential_moving_average(close: pd.Series, period: int) -> pd.Series:
    """Return the causal EMA for one frozen candidate period."""
    period = int(period)
    if period <= 0:
        raise ValueError("EMA period must be positive")
    return _close_series(close).ewm(span=period, adjust=False).mean()


def relative_strength_index(close: pd.Series, period: int = 14) -> pd.Series:
    """Return Wilder-smoothed RSI for one frozen candidate period."""
    period = int(period)
    if period <= 0:
        raise ValueError("RSI period must be positive")

    close_series = _close_series(close)
    delta = close_series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    average_gain = gain.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False,
    ).mean()
    average_loss = loss.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False,
    ).mean()
    relative_strength = average_gain / average_loss.replace(0.0, math.nan)
    rsi = 100.0 - (100.0 / (1.0 + relative_strength))
    rsi = rsi.where(average_loss != 0.0, 100.0)
    return rsi.where(average_gain != 0.0, 0.0)


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
    fast_ema = exponential_moving_average(close_series, fast)
    slow_ema = exponential_moving_average(close_series, slow)
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


def average_true_range(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Return Wilder-smoothed ATR for one frozen candidate period."""
    period = int(period)
    if period <= 0:
        raise ValueError("ATR period must be positive")

    high_series = pd.Series(high, index=high.index, dtype=float)
    low_series = pd.Series(low, index=low.index, dtype=float)
    close_series = _close_series(close)
    if high_series.empty or low_series.empty:
        raise ValueError("high and low must contain at least one value")
    if not high_series.index.equals(close_series.index) or not low_series.index.equals(
        close_series.index
    ):
        raise ValueError("high, low, and close must use identical indexes")

    previous_close = close_series.shift(1)
    true_range = pd.concat(
        [
            high_series - low_series,
            (high_series - previous_close).abs(),
            (low_series - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False,
    ).mean()


def stochastic_oscillator(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k: int = 14,
    d: int = 3,
    smooth: int | None = 3,
) -> tuple[pd.Series, pd.Series]:
    """Return stochastic %K and %D for one frozen candidate parameter set."""
    k = int(k)
    d = int(d)
    if k <= 0 or d <= 0:
        raise ValueError("Stochastic k and d periods must be positive")
    if smooth is None or smooth == "" or smooth is False:
        smooth_period = None
    else:
        smooth_period = int(smooth)
        if smooth_period <= 0:
            raise ValueError("Stochastic smooth period must be positive")

    high_series = pd.Series(high, index=high.index, dtype=float)
    low_series = pd.Series(low, index=low.index, dtype=float)
    close_series = _close_series(close)
    if high_series.empty or low_series.empty:
        raise ValueError("high and low must contain at least one value")
    if not high_series.index.equals(close_series.index) or not low_series.index.equals(
        close_series.index
    ):
        raise ValueError("high, low, and close must use identical indexes")

    lowest_low = low_series.rolling(k).min()
    highest_high = high_series.rolling(k).max()
    raw_k = (close_series - lowest_low) / (highest_high - lowest_low).replace(
        0.0, math.nan
    ) * 100.0
    if smooth_period is not None and smooth_period > 1:
        raw_k = raw_k.rolling(smooth_period).mean()
    return raw_k, raw_k.rolling(d).mean()
