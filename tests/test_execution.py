from pathlib import Path

import numpy as np
import pytest

from xauusd_ea.baseline import (
    assert_runtime_broker_spec_matches_profile,
    load_broker_profile,
)
from xauusd_ea.execution import apply_execution_price, commission_per_side


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


def test_bid_execution_applies_full_spread_only_to_buy_side():
    spec = _runtime_spec()
    friction = {"slippage_mode": "fixed", "slippage_value": 10.0}

    buy, buy_cost = apply_execution_price(3300.0, "buy", friction, spec)
    sell, sell_cost = apply_execution_price(3300.0, "sell", friction, spec)

    assert buy == pytest.approx(3300.0 + spec["spread_baseline_price"] + 0.10)
    assert sell == pytest.approx(3299.90)
    assert buy_cost["spread_component"] == pytest.approx(
        spec["spread_baseline_price"]
    )
    assert sell_cost["spread_component"] == 0.0
    assert buy_cost["ohlc_price_source"] == "bid"


def test_supported_stress_spread_is_applied_without_mutating_broker_constants():
    spec = _runtime_spec()
    stress_points = spec["spread_points"] * 2.0

    executed, costs = apply_execution_price(
        3300.0,
        "buy",
        {
            "spread_points": stress_points,
            "slippage_mode": "fixed",
            "slippage_value": 0.0,
        },
        spec,
    )

    assert executed == pytest.approx(3300.0 + spec["spread_baseline_price"] * 2.0)
    assert costs["spread_total"] == pytest.approx(
        spec["spread_baseline_price"] * 2.0
    )
    assert spec["spread_points"] != stress_points


def test_random_slippage_is_reproducible_with_an_injected_rng():
    spec = _runtime_spec()
    friction = {
        "slippage_mode": "random_normal",
        "slippage_mu": 5.0,
        "slippage_sigma": 1.0,
    }

    first = apply_execution_price(
        3300.0, "sell", friction, spec, rng=np.random.default_rng(42)
    )
    second = apply_execution_price(
        3300.0, "sell", friction, spec, rng=np.random.default_rng(42)
    )

    assert first == second


def test_execution_rejects_unapproved_spread_or_unknown_slippage_mode():
    spec = _runtime_spec()

    with pytest.raises(ValueError, match="audited baseline/stress spreads"):
        apply_execution_price(3300.0, "buy", {"spread_points": 1.0}, spec)
    with pytest.raises(ValueError, match="unsupported slippage_mode"):
        apply_execution_price(
            3300.0,
            "buy",
            {"slippage_mode": "mystery"},
            spec,
        )


def test_commission_uses_verified_zero_rate_and_rejects_conflicts():
    spec = _runtime_spec()

    assert commission_per_side(0.1, {}, spec) == 0.0
    with pytest.raises(ValueError, match="conflicts with the verified runtime"):
        commission_per_side(0.1, {"commission_per_lot_round_turn": 7.0}, spec)
    with pytest.raises(ValueError, match="non-negative"):
        commission_per_side(-0.1, {}, spec)
