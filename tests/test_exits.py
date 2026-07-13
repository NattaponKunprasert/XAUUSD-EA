from pathlib import Path

import pandas as pd
import pytest

from xauusd_ea.baseline import (
    assert_runtime_broker_spec_matches_profile,
    load_broker_profile,
)
from xauusd_ea.exits import (
    fibonacci_extension_target,
    indicator_reversal_exit_due,
    initial_stop_target,
    max_holding_exit_due,
    next_trailing_stop,
    resolve_intrabar_stop_target,
)


ROOT = Path(__file__).resolve().parents[1]


def _runtime_spec() -> dict:
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    return assert_runtime_broker_spec_matches_profile(broker.to_runtime_spec(), broker)


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "high": [100.0, 102.0, 105.0, 500.0],
            "low": [98.0, 99.0, 101.0, 1.0],
        }
    )


@pytest.mark.parametrize(
    ("direction", "long_signal", "short_signal", "expected"),
    [
        ("long", False, True, True),
        ("long", True, False, False),
        ("short", True, False, True),
        ("short", False, True, False),
    ],
)
def test_indicator_reversal_exit_uses_only_the_opposite_closed_bar_signal(
    direction, long_signal, short_signal, expected
):
    assert (
        indicator_reversal_exit_due(direction, long_signal, short_signal) is expected
    )


@pytest.mark.parametrize(
    ("direction", "long_signal", "short_signal", "message"),
    [
        ("flat", False, False, "direction"),
        ("long", 1, False, "long_signal"),
        ("short", False, "yes", "short_signal"),
    ],
)
def test_indicator_reversal_exit_rejects_ambiguous_state(
    direction, long_signal, short_signal, message
):
    with pytest.raises(ValueError, match=message):
        indicator_reversal_exit_due(direction, long_signal, short_signal)


@pytest.mark.parametrize(
    ("direction", "expected_stop", "expected_target"),
    [
        ("long", 98.0, 110.0),
        ("short", 110.0, 98.0),
    ],
)
def test_initial_atr_stop_rr_target_is_directional(
    direction, expected_stop, expected_target
):
    levels = initial_stop_target(
        104.0,
        3.0,
        _bars(),
        signal_index=2,
        direction=direction,
        exit_config={
            "sl_type": "atr",
            "atr_multiplier": 2.0,
            "tp_type": "rr",
            "risk_reward_ratio": 1.0,
        },
    )

    assert levels == pytest.approx((expected_stop, expected_target))


def test_initial_structure_stop_uses_only_closed_bars_through_signal():
    original = _bars()
    mutated_future = original.copy()
    mutated_future.loc[3, ["high", "low"]] = [5000.0, -5000.0]

    config = {
        "sl_type": "structure",
        "structure_window": 3,
        "tp_type": "rr",
        "risk_reward_ratio": 2.0,
    }
    original_levels = initial_stop_target(
        106.0, None, original, 2, "long", config
    )
    mutated_levels = initial_stop_target(
        106.0, None, mutated_future, 2, "long", config
    )

    assert original_levels == pytest.approx((98.0, 122.0))
    assert mutated_levels == pytest.approx(original_levels)


def test_initial_stop_target_returns_none_for_invalid_market_geometry():
    frame = pd.DataFrame({"high": [110.0], "low": [105.0]})

    assert initial_stop_target(
        100.0,
        None,
        frame,
        0,
        "long",
        {"sl_type": "structure", "tp_type": "rr"},
    ) is None


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"sl_type": "mystery", "tp_type": "rr"}, "sl_type"),
        ({"sl_type": "atr", "tp_type": "mystery"}, "tp_type"),
        (
            {"sl_type": "atr", "atr_multiplier": 0, "tp_type": "rr"},
            "atr_multiplier",
        ),
    ],
)
def test_initial_stop_target_rejects_unsafe_configuration(config, message):
    with pytest.raises(ValueError, match=message):
        initial_stop_target(104.0, 3.0, _bars(), 2, "long", config)


def test_intrabar_long_gap_and_same_bar_conflict_are_conservative():
    spec = _runtime_spec()
    position = {
        "direction": "long",
        "stop_loss": 1995.0,
        "take_profit": 2010.0,
        "stop_loss_is_trailing": False,
    }

    assert resolve_intrabar_stop_target(
        position, 1994.0, 2002.0, 1990.0, {}, spec
    ) == (1994.0, "SL")
    assert resolve_intrabar_stop_target(
        position, 2000.0, 2012.0, 1992.0, {}, spec
    ) == (1995.0, "SL")


def test_intrabar_short_uses_ask_triggers_and_returns_raw_bid():
    spec = _runtime_spec()
    spread = spec["spread_points"] * spec["point"]
    position = {
        "direction": "short",
        "stop_loss": 2005.0,
        "take_profit": 1990.0,
        "stop_loss_is_trailing": False,
    }

    raw_exit, reason = resolve_intrabar_stop_target(
        position,
        2000.0,
        2005.0 - spread,
        1988.0,
        {},
        spec,
    )

    assert raw_exit == pytest.approx(2005.0 - spread)
    assert reason == "SL"


def test_intrabar_trailing_reason_and_invalid_state_fail_closed():
    spec = _runtime_spec()
    trailing = {
        "direction": "long",
        "stop_loss": 2001.0,
        "take_profit": 2010.0,
        "stop_loss_is_trailing": True,
    }
    assert resolve_intrabar_stop_target(
        trailing, 2005.0, 2008.0, 2000.0, {}, spec
    ) == (2001.0, "TrailingStop")

    with pytest.raises(ValueError, match="low <= open <= high"):
        resolve_intrabar_stop_target(trailing, 2005.0, 2004.0, 2000.0, {}, spec)

    conflicting = dict(spec)
    conflicting["contract_size"] = 100.0
    with pytest.raises(ValueError, match="no longer matches"):
        resolve_intrabar_stop_target(
            trailing, 2005.0, 2008.0, 2000.0, {}, conflicting
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


def test_max_holding_exit_is_due_exactly_at_the_configured_bar_limit():
    assert not max_holding_exit_due(10, 10, 3)
    assert not max_holding_exit_due(10, 12, 3)
    assert max_holding_exit_due(10, 13, 3)
    assert max_holding_exit_due(10, 14, 3)


@pytest.mark.parametrize("disabled_limit", [0, -1])
def test_max_holding_exit_non_positive_limits_are_disabled(disabled_limit):
    assert not max_holding_exit_due(10, 100, disabled_limit)


@pytest.mark.parametrize(
    ("entry_index", "current_index", "max_bars", "message"),
    [
        (-1, 0, 3, "non-negative entry_index"),
        (4, 3, 3, "at or after"),
        (1.5, 3, 3, "entry_index must be an integer"),
        (1, 3, 3.0, "max_holding_bars must be an integer"),
    ],
)
def test_max_holding_exit_rejects_invalid_index_state(
    entry_index, current_index, max_bars, message
):
    with pytest.raises(ValueError, match=message):
        max_holding_exit_due(entry_index, current_index, max_bars)


def test_atr_trailing_stop_is_directional_and_never_moves_backwards():
    spec = _runtime_spec()

    assert next_trailing_stop(
        2000.0,
        1990.0,
        2010.0,
        "long",
        "atr",
        {"trail_multiplier": 2.0},
        spec,
        current_atr=4.0,
    ) == pytest.approx(2002.0)
    assert next_trailing_stop(
        2000.0,
        2010.0,
        1990.0,
        "short",
        "atr",
        {"trail_multiplier": 2.0},
        spec,
        current_atr=4.0,
    ) == pytest.approx(1998.0)
    assert next_trailing_stop(
        2000.0,
        2005.0,
        2010.0,
        "long",
        "atr",
        {"trail_multiplier": 2.0},
        spec,
        current_atr=4.0,
    ) is None


def test_percent_and_step_trails_preserve_active_engine_math():
    spec = _runtime_spec()

    assert next_trailing_stop(
        2000.0, 1980.0, 2020.0, "long", "percent", {"trail_percent": 0.5}, spec
    ) == pytest.approx(2009.9)
    assert next_trailing_stop(
        2000.0, 1990.0, 2001.2, "long", "step", {"trail_step_pips": 50}, spec
    ) == pytest.approx(2000.5)
    assert next_trailing_stop(
        2000.0, 2010.0, 1998.8, "short", "step", {"trail_step_pips": 50}, spec
    ) == pytest.approx(1999.5)


def test_trailing_stop_rejects_invalid_configuration_and_broker_conflict():
    spec = _runtime_spec()
    with pytest.raises(ValueError, match="trail_type must be"):
        next_trailing_stop(2000.0, 1990.0, 2010.0, "long", "mystery", {}, spec)
    with pytest.raises(ValueError, match="trail_percent"):
        next_trailing_stop(
            2000.0, 1990.0, 2010.0, "long", "percent", {"trail_percent": 0}, spec
        )

    conflicting = dict(spec)
    conflicting["contract_size"] = 100.0
    with pytest.raises(ValueError, match="no longer matches"):
        next_trailing_stop(
            2000.0, 1990.0, 2010.0, "long", "percent", {}, conflicting
        )
