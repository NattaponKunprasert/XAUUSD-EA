import pandas as pd
import pytest

from xauusd_ea.indicators import bollinger_bands, macd


def _close() -> pd.Series:
    return pd.Series(
        [100.0, 101.0, 99.0, 103.0, 102.0, 106.0, 104.0, 108.0],
        index=pd.date_range("2025-01-01", periods=8, freq="15min"),
    )


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
