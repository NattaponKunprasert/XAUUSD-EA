import pandas as pd
import pytest

from xauusd_ea.exits import fibonacci_extension_target


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "high": [100.0, 102.0, 105.0, 500.0],
            "low": [98.0, 99.0, 101.0, 1.0],
        }
    )


def test_fibonacci_target_uses_only_closed_bars_through_signal_index():
    target = fibonacci_extension_target(
        106.0,
        _bars(),
        signal_index=2,
        direction="long",
        fib_levels=[1.618],
        lookback=3,
    )

    assert target == pytest.approx(106.0 + (105.0 - 98.0) * 1.618)


def test_fibonacci_target_is_directional_and_uses_furthest_configured_level():
    long_target = fibonacci_extension_target(
        106.0, _bars(), 2, "long", [161.8, 2.0], lookback=3
    )
    short_target = fibonacci_extension_target(
        97.0, _bars(), 2, "short", [1.618, 200.0], lookback=3
    )

    assert long_target == pytest.approx(120.0)
    assert short_target == pytest.approx(83.0)


@pytest.mark.parametrize(
    ("levels", "message"),
    [([], "at least one"), ([1.5], "unsupported Fibonacci extension")],
)
def test_fibonacci_target_rejects_missing_or_unapproved_levels(levels, message):
    with pytest.raises(ValueError, match=message):
        fibonacci_extension_target(106.0, _bars(), 2, "long", levels)


def test_fibonacci_target_rejects_flat_closed_bar_range():
    flat = pd.DataFrame({"high": [100.0, 100.0], "low": [100.0, 100.0]})

    with pytest.raises(ValueError, match="swing range must be positive"):
        fibonacci_extension_target(100.0, flat, 1, "long", [1.618])
