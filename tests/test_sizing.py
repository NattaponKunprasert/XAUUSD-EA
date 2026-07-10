from pathlib import Path

import pytest

from xauusd_ea.baseline import (
    assert_runtime_broker_spec_matches_profile,
    load_broker_profile,
)
from xauusd_ea.sizing import calculate_position_size


ROOT = Path(__file__).resolve().parents[1]


def _runtime_spec() -> dict:
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    return assert_runtime_broker_spec_matches_profile(
        {
            **broker.to_runtime_spec(),
            "lot_precision": 2,
            "spread_application": "full",
            "cost_value_mode": "points",
            "spread_points": broker.spread_baseline_price / broker.point,
            "commission_per_lot_round_turn": 0.0,
            "fee_per_lot_round_turn": 0.0,
            "swap_per_lot": broker.swap_long_points * broker.point,
            "swap_long_per_lot": broker.swap_long_points * broker.point,
            "swap_short_per_lot": broker.swap_short_points * broker.point,
        },
        broker,
    )


def test_risk_percent_size_floors_without_exceeding_cash_risk():
    spec = _runtime_spec()

    lot = calculate_position_size(
        1000.0,
        2000.0,
        1994.0,
        sizing_method="risk_percent",
        config={"risk_percent": 0.1},
        runtime_spec=spec,
    )

    assert lot == 0.16
    assert (2000.0 - 1994.0) * lot * spec["contract_size"] <= 1.0


def test_risk_percent_size_below_minimum_is_no_trade():
    assert calculate_position_size(
        1000.0,
        2000.0,
        1980.0,
        sizing_method="risk_percent",
        config={"risk_percent": 0.1},
        runtime_spec=_runtime_spec(),
    ) == 0.0


def test_fixed_size_is_floored_and_capped_to_verified_volume_bounds():
    spec = _runtime_spec()

    assert calculate_position_size(
        1000.0, 2000.0, 1990.0, config={"fixed_lot": 0.109}, runtime_spec=spec
    ) == 0.10
    assert calculate_position_size(
        1000.0, 2000.0, 1990.0, config={"fixed_lot": 100.5}, runtime_spec=spec
    ) == 100.0


def test_atr_size_uses_frozen_atr_and_explicit_divider_precedence():
    spec = _runtime_spec()

    assert calculate_position_size(
        1000.0,
        2000.0,
        1990.0,
        sizing_method="atr_based",
        config={"base_lot_size": 0.5, "atr": 2.0, "atr_multiplier": 1.0},
        runtime_spec=spec,
    ) == 0.25
    assert calculate_position_size(
        1000.0,
        2000.0,
        1990.0,
        sizing_method="atr_based",
        config={
            "base_lot_size": 0.5,
            "atr": 2.0,
            "atr_multiplier": 1.0,
            "volatility_divider": 4.0,
        },
        runtime_spec=spec,
    ) == 0.12


@pytest.mark.parametrize(
    "config",
    [
        {"base_lot_size": 0.5},
        {"base_lot_size": 0.5, "atr": 0.0},
        {"base_lot_size": 0.5, "atr": float("nan")},
    ],
)
def test_atr_size_fails_closed_without_positive_finite_volatility(config):
    assert calculate_position_size(
        1000.0,
        2000.0,
        1990.0,
        sizing_method="atr_based",
        config=config,
        runtime_spec=_runtime_spec(),
    ) == 0.0


def test_sizing_rejects_unknown_method_and_broker_constant_conflict():
    spec = _runtime_spec()

    with pytest.raises(ValueError, match="Invalid sizing method"):
        calculate_position_size(
            1000.0,
            2000.0,
            1990.0,
            sizing_method="mystery",
            runtime_spec=spec,
        )
    with pytest.raises(ValueError, match="conflicts with the verified runtime"):
        calculate_position_size(
            1000.0,
            2000.0,
            1990.0,
            config={"fixed_lot": 0.1, "contract_size": 100.0},
            runtime_spec=spec,
        )
