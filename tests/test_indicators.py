import pandas as pd
import pytest

from xauusd_ea.indicators import (
    average_true_range,
    bollinger_bands,
    exponential_moving_average,
    macd,
    relative_strength_index,
)


def _close() -> pd.Series:
    return pd.Series(
        [100.0, 101.0, 99.0, 103.0, 102.0, 106.0, 104.0, 108.0],
        index=pd.date_range("2025-01-01", periods=8, freq="15min"),
    )


def _ohlc() -> tuple[pd.Series, pd.Series, pd.Series]:
    close = _close()
    return close + 2.0, close - 1.0, close


def test_exponential_moving_average_uses_frozen_candidate_period():
    close = _close()
    ema_two = exponential_moving_average(close, period=2)
    ema_four = exponential_moving_average(close, period=4)

    pd.testing.assert_series_equal(
        ema_two,
        close.ewm(span=2, adjust=False).mean(),
    )
    assert not ema_two.equals(ema_four)


def test_exponential_moving_average_ignores_future_close_mutations():
    close = _close()
    original = exponential_moving_average(close, period=3)
    mutated = close.copy()
    mutated.iloc[6:] = [500.0, 1.0]

    pd.testing.assert_series_equal(
        original.iloc[:6],
        exponential_moving_average(mutated, period=3).iloc[:6],
    )


def test_exponential_moving_average_rejects_invalid_period():
    with pytest.raises(ValueError, match="positive"):
        exponential_moving_average(_close(), period=0)


def test_relative_strength_index_uses_frozen_candidate_period():
    close = _close()
    rsi_two = relative_strength_index(close, period=2)
    rsi_four = relative_strength_index(close, period=4)

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    average_gain = gain.ewm(alpha=0.5, min_periods=2, adjust=False).mean()
    average_loss = loss.ewm(alpha=0.5, min_periods=2, adjust=False).mean()
    relative_strength = average_gain / average_loss.replace(0.0, float("nan"))
    expected = 100.0 - (100.0 / (1.0 + relative_strength))
    expected = expected.where(average_loss != 0.0, 100.0)
    expected = expected.where(average_gain != 0.0, 0.0)

    pd.testing.assert_series_equal(rsi_two, expected)
    assert not rsi_two.equals(rsi_four)


def test_relative_strength_index_ignores_future_close_mutations():
    close = _close()
    original = relative_strength_index(close, period=3)
    mutated = close.copy()
    mutated.iloc[6:] = [500.0, 1.0]

    pd.testing.assert_series_equal(
        original.iloc[:6],
        relative_strength_index(mutated, period=3).iloc[:6],
    )


def test_relative_strength_index_rejects_invalid_period():
    with pytest.raises(ValueError, match="positive"):
        relative_strength_index(_close(), period=0)


def test_macd_uses_the_candidate_parameter_set():
    close = _close()
    line_a, signal_a, histogram_a = macd(close, fast=2, slow=5, signal=2)
    line_b, signal_b, histogram_b = macd(close, fast=3, slow=6, signal=3)

    expected_line = (
        close.ewm(span=2, adjust=False).mean()
        - close.ewm(span=5, adjust=False).mean()
    )
    pd.testing.assert_series_equal(line_a, expected_line)
    pd.testing.assert_series_equal(
        signal_a, expected_line.ewm(span=2, adjust=False).mean()
    )
    pd.testing.assert_series_equal(histogram_a, line_a - signal_a)
    assert not line_a.equals(line_b)
    assert not signal_a.equals(signal_b)
    assert not histogram_a.equals(histogram_b)


def test_bollinger_bands_use_candidate_period_and_multiplier():
    close = _close()
    middle_a, upper_a, lower_a = bollinger_bands(close, period=3, multiplier=1.5)
    middle_b, upper_b, lower_b = bollinger_bands(close, period=4, multiplier=2.5)

    expected_middle = close.rolling(3).mean()
    expected_deviation = close.rolling(3).std(ddof=0)
    pd.testing.assert_series_equal(middle_a, expected_middle)
    pd.testing.assert_series_equal(upper_a, expected_middle + 1.5 * expected_deviation)
    pd.testing.assert_series_equal(lower_a, expected_middle - 1.5 * expected_deviation)
    assert not middle_a.equals(middle_b)
    assert not upper_a.equals(upper_b)
    assert not lower_a.equals(lower_b)


def test_indicator_values_do_not_change_when_only_future_closes_change():
    close = _close()
    mutated = close.copy()
    mutated.iloc[6:] = [500.0, 1.0]

    original_macd = macd(close, fast=2, slow=5, signal=2)
    mutated_macd = macd(mutated, fast=2, slow=5, signal=2)
    original_bands = bollinger_bands(close, period=3, multiplier=1.5)
    mutated_bands = bollinger_bands(mutated, period=3, multiplier=1.5)

    for original, changed in zip(original_macd + original_bands, mutated_macd + mutated_bands):
        pd.testing.assert_series_equal(original.iloc[:6], changed.iloc[:6])


def test_average_true_range_uses_candidate_period_and_wilder_smoothing():
    high, low, close = _ohlc()
    atr_two = average_true_range(high, low, close, period=2)
    atr_four = average_true_range(high, low, close, period=4)

    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    expected = true_range.ewm(alpha=0.5, min_periods=2, adjust=False).mean()
    pd.testing.assert_series_equal(atr_two, expected)
    assert not atr_two.equals(atr_four)


def test_average_true_range_ignores_future_ohlc_mutations():
    high, low, close = _ohlc()
    original = average_true_range(high, low, close, period=3)
    high.iloc[6:] = [900.0, 800.0]
    low.iloc[6:] = [1.0, 2.0]
    close.iloc[6:] = [500.0, 3.0]
    mutated = average_true_range(high, low, close, period=3)

    pd.testing.assert_series_equal(original.iloc[:6], mutated.iloc[:6])


@pytest.mark.parametrize(
    ("args", "message"),
    [((0, 5, 2), "positive"), ((5, 5, 2), "less than slow")],
)
def test_macd_rejects_invalid_candidate_periods(args, message):
    with pytest.raises(ValueError, match=message):
        macd(_close(), *args)


@pytest.mark.parametrize(
    ("period", "multiplier", "message"),
    [(1, 2.0, "greater than one"), (3, 0.0, "finite and positive")],
)
def test_bollinger_rejects_invalid_candidate_parameters(period, multiplier, message):
    with pytest.raises(ValueError, match=message):
        bollinger_bands(_close(), period, multiplier)


def test_average_true_range_rejects_invalid_period_or_misaligned_prices():
    high, low, close = _ohlc()
    with pytest.raises(ValueError, match="positive"):
        average_true_range(high, low, close, 0)
    with pytest.raises(ValueError, match="identical indexes"):
        average_true_range(high.reset_index(drop=True), low, close, 3)
