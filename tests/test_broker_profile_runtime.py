from pathlib import Path

import pytest

from xauusd_ea.baseline import (
    _verified_runtime_spec_fingerprint,
    assert_runtime_broker_spec_matches_profile,
    load_broker_profile,
    merge_runtime_broker_overrides,
    require_runtime_broker_spec,
)

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_spec_exports_verified_xm_micro_config():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")

    runtime_spec = broker.to_runtime_spec()

    assert runtime_spec["symbol"] == "GOLDmicro"
    assert runtime_spec["aliases"] == ["XAUUSD", "GOLD"]
    assert runtime_spec["digits"] == 2
    assert runtime_spec["contract_size"] == 1.0
    assert runtime_spec["point"] == 0.01
    assert runtime_spec["ohlc_price_source"] == "bid"
    assert runtime_spec["spread_mode"] == "floating"
    assert runtime_spec["min_lot"] == 0.1
    assert runtime_spec["max_lot"] == 100.0
    assert runtime_spec["lot_step"] == 0.01
    assert runtime_spec["swap_long_points"] == pytest.approx(-93.39)
    assert runtime_spec["swap_short_points"] == pytest.approx(10.74)


def test_runtime_spec_match_accepts_verified_constants_and_keeps_extra_fields():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    runtime_spec = {
        **broker.to_runtime_spec(),
        "lot_precision": 2,
        "spread_application": "full",
        "spread_points": broker.spread_baseline_price / broker.point,
        "commission_per_lot_round_turn": broker.commission_per_lot_round_turn_usd,
        "fee_per_lot_round_turn": broker.fee_per_lot_round_turn_usd,
        "swap_per_lot": broker.swap_long_points * broker.point * broker.contract_size,
        "swap_long_per_lot": (
            broker.swap_long_points * broker.point * broker.contract_size
        ),
        "swap_short_per_lot": (
            broker.swap_short_points * broker.point * broker.contract_size
        ),
    }

    merged = assert_runtime_broker_spec_matches_profile(runtime_spec, broker)

    assert merged["symbol"] == "GOLDmicro"
    assert merged["lot_precision"] == 2
    assert merged["spread_application"] == "full"
    assert "verified_runtime_spec_fingerprint" in merged


def test_runtime_spec_match_fills_verified_derived_runtime_aliases():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")

    merged = assert_runtime_broker_spec_matches_profile(
        broker.to_runtime_spec(),
        broker,
    )

    assert merged["cost_value_mode"] == "points"
    assert merged["spread_points"] == pytest.approx(
        broker.spread_baseline_price / broker.point
    )
    assert merged["commission_per_lot_round_turn"] == pytest.approx(0.0)
    assert merged["fee_per_lot_round_turn"] == pytest.approx(0.0)
    assert merged["swap_per_lot"] == pytest.approx(-0.9339)
    assert merged["swap_long_per_lot"] == pytest.approx(-0.9339)
    assert merged["swap_short_per_lot"] == pytest.approx(0.1074)


def test_runtime_spec_match_rejects_legacy_xauusd_defaults():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    legacy_spec = {
        **broker.to_runtime_spec(),
        "symbol": "XAUUSD",
        "contract_size": 100.0,
        "min_lot": 0.01,
        "max_lot": 50.0,
        "spread_mode": "fixed",
    }

    with pytest.raises(
        ValueError,
        match="symbol: got 'XAUUSD', expected 'GOLDmicro'",
    ):
        assert_runtime_broker_spec_matches_profile(legacy_spec, broker)


def test_runtime_spec_match_rejects_legacy_spread_and_account_costs():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    legacy_cost_spec = {
        **broker.to_runtime_spec(),
        "spread_baseline_price": 1.5,
        "spread_stress_multipliers": [1.0],
        "initial_capital_usd": 10_000.0,
        "swap_long_points": -100.0,
        "swap_short_points": -100.0,
    }

    with pytest.raises(
        ValueError,
        match="spread_baseline_price: got 1.5, expected 0.551142857142857",
    ):
        assert_runtime_broker_spec_matches_profile(legacy_cost_spec, broker)


def test_runtime_spec_match_rejects_conflicting_derived_cost_aliases():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    conflicting_runtime_spec = {
        **broker.to_runtime_spec(),
        "cost_value_mode": "price",
        "spread_points": 150.0,
        "commission_per_lot_round_turn": 7.0,
        "swap_long_per_lot": -1.0,
    }

    with pytest.raises(
        ValueError,
        match="cost_value_mode: got 'price', expected 'points'",
    ):
        assert_runtime_broker_spec_matches_profile(conflicting_runtime_spec, broker)


def test_runtime_spec_match_rejects_missing_required_verified_fields():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    incomplete_spec = {
        "symbol": "GOLDmicro",
        "contract_size": 1.0,
    }

    with pytest.raises(ValueError, match="digits: missing; expected 2"):
        assert_runtime_broker_spec_matches_profile(incomplete_spec, broker)


def test_require_runtime_broker_spec_accepts_checked_runtime_spec():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    checked_runtime_spec = assert_runtime_broker_spec_matches_profile(
        {
            **broker.to_runtime_spec(),
            "lot_precision": 2,
            "cost_value_mode": "points",
            "spread_points": broker.spread_baseline_price / broker.point,
            "commission_per_lot_round_turn": (
                broker.commission_per_lot_round_turn_usd
            ),
            "swap_per_lot": (
                broker.swap_long_points * broker.point * broker.contract_size
            ),
        },
        broker,
    )
    runtime_spec = require_runtime_broker_spec(checked_runtime_spec)

    assert runtime_spec["symbol"] == "GOLDmicro"
    assert runtime_spec["spread_points"] == pytest.approx(55.1142857142857)
    assert runtime_spec["swap_long_per_lot"] == pytest.approx(-0.9339)
    assert runtime_spec["swap_short_per_lot"] == pytest.approx(0.1074)


def test_merge_runtime_broker_overrides_rejects_conflicting_verified_fields():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    runtime_spec = assert_runtime_broker_spec_matches_profile(
        {
            **broker.to_runtime_spec(),
            "lot_precision": 2,
            "cost_value_mode": "points",
            "spread_points": broker.spread_baseline_price / broker.point,
            "commission_per_lot_round_turn": (
                broker.commission_per_lot_round_turn_usd
            ),
            "swap_per_lot": (
                broker.swap_long_points * broker.point * broker.contract_size
            ),
        },
        broker,
    )

    with pytest.raises(
        ValueError,
        match="calculate_position_size conflicts with the verified runtime broker spec",
    ):
        merge_runtime_broker_overrides(
            runtime_spec,
            {"contract_size": 100.0, "fixed_lot": 0.1},
            context="calculate_position_size",
        )


def test_merge_runtime_broker_overrides_allows_supported_spread_stress_values():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    runtime_spec = assert_runtime_broker_spec_matches_profile(
        {
            **broker.to_runtime_spec(),
            "lot_precision": 2,
            "cost_value_mode": "points",
            "spread_points": broker.spread_baseline_price / broker.point,
            "commission_per_lot_round_turn": (
                broker.commission_per_lot_round_turn_usd
            ),
            "swap_per_lot": (
                broker.swap_long_points * broker.point * broker.contract_size
            ),
        },
        broker,
    )

    merged = merge_runtime_broker_overrides(
        runtime_spec,
        {
            "spread_points": runtime_spec["spread_points"] * 1.5,
            "slippage_mode": "fixed",
        },
        context="_spread_price",
        allow_supported_spread_override=True,
    )

    assert merged["spread_points"] == pytest.approx(runtime_spec["spread_points"] * 1.5)
    assert merged["slippage_mode"] == "fixed"


def test_merge_runtime_broker_overrides_rejects_unsupported_spread_override():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    runtime_spec = assert_runtime_broker_spec_matches_profile(
        {
            **broker.to_runtime_spec(),
            "lot_precision": 2,
            "cost_value_mode": "points",
            "spread_points": broker.spread_baseline_price / broker.point,
            "commission_per_lot_round_turn": (
                broker.commission_per_lot_round_turn_usd
            ),
            "swap_per_lot": (
                broker.swap_long_points * broker.point * broker.contract_size
            ),
        },
        broker,
    )

    with pytest.raises(
        ValueError,
        match="is not one of the audited baseline/stress spreads",
    ):
        merge_runtime_broker_overrides(
            runtime_spec,
            {"spread_points": 150.0},
            context="_spread_price",
            allow_supported_spread_override=True,
        )


def test_require_runtime_broker_spec_rejects_unverified_runtime_spec_snapshot():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")

    with pytest.raises(
        ValueError,
        match="missing its verified profile fingerprint",
    ):
        require_runtime_broker_spec(
            {
                **broker.to_runtime_spec(),
                "cost_value_mode": "points",
                "spread_points": broker.spread_baseline_price / broker.point,
                "commission_per_lot_round_turn": (
                    broker.commission_per_lot_round_turn_usd
                ),
                "fee_per_lot_round_turn": broker.fee_per_lot_round_turn_usd,
                "swap_per_lot": (
                    broker.swap_long_points * broker.point * broker.contract_size
                ),
                "swap_long_per_lot": (
                    broker.swap_long_points * broker.point * broker.contract_size
                ),
                "swap_short_per_lot": (
                    broker.swap_short_points * broker.point * broker.contract_size
                ),
            }
        )


def test_require_runtime_broker_spec_rejects_post_verification_mutation():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    checked_runtime_spec = assert_runtime_broker_spec_matches_profile(
        {
            **broker.to_runtime_spec(),
            "cost_value_mode": "points",
            "spread_points": broker.spread_baseline_price / broker.point,
            "commission_per_lot_round_turn": (
                broker.commission_per_lot_round_turn_usd
            ),
            "swap_per_lot": (
                broker.swap_long_points * broker.point * broker.contract_size
            ),
        },
        broker,
    )
    checked_runtime_spec["contract_size"] = 100.0

    with pytest.raises(
        ValueError,
        match="no longer matches the verified config/xm_micro_gold.json snapshot",
    ):
        require_runtime_broker_spec(checked_runtime_spec)


def test_require_runtime_broker_spec_rejects_post_verification_cost_mode_mutation():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    checked_runtime_spec = assert_runtime_broker_spec_matches_profile(
        {
            **broker.to_runtime_spec(),
            "cost_value_mode": "points",
            "spread_points": broker.spread_baseline_price / broker.point,
            "commission_per_lot_round_turn": (
                broker.commission_per_lot_round_turn_usd
            ),
            "swap_per_lot": (
                broker.swap_long_points * broker.point * broker.contract_size
            ),
        },
        broker,
    )
    checked_runtime_spec["cost_value_mode"] = "price"

    with pytest.raises(
        ValueError,
        match="no longer matches the verified config/xm_micro_gold.json snapshot",
    ):
        require_runtime_broker_spec(checked_runtime_spec)


def test_require_runtime_broker_spec_rejects_forged_fingerprint_for_mutated_values():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    checked_runtime_spec = assert_runtime_broker_spec_matches_profile(
        {
            **broker.to_runtime_spec(),
            "cost_value_mode": "points",
            "spread_points": broker.spread_baseline_price / broker.point,
            "commission_per_lot_round_turn": (
                broker.commission_per_lot_round_turn_usd
            ),
            "fee_per_lot_round_turn": broker.fee_per_lot_round_turn_usd,
            "swap_per_lot": (
                broker.swap_long_points * broker.point * broker.contract_size
            ),
            "swap_long_per_lot": (
                broker.swap_long_points * broker.point * broker.contract_size
            ),
            "swap_short_per_lot": (
                broker.swap_short_points * broker.point * broker.contract_size
            ),
        },
        broker,
    )
    checked_runtime_spec["contract_size"] = 100.0
    checked_runtime_spec["verified_runtime_spec_fingerprint"] = (
        _verified_runtime_spec_fingerprint(checked_runtime_spec)
    )

    with pytest.raises(
        ValueError,
        match="no longer matches the verified config/xm_micro_gold.json snapshot",
    ):
        require_runtime_broker_spec(checked_runtime_spec)


def test_require_runtime_broker_spec_rejects_missing_verified_runtime_fields():
    with pytest.raises(
        ValueError,
        match="missing verified fields required by active notebook helpers",
    ):
        require_runtime_broker_spec(
            {
                "symbol": "GOLDmicro",
                "contract_size": 1.0,
                "point": 0.01,
                "min_lot": 0.1,
                "max_lot": 100.0,
            }
        )


def test_require_runtime_broker_spec_rejects_missing_directional_swap_aliases():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    checked_runtime_spec = assert_runtime_broker_spec_matches_profile(
        broker.to_runtime_spec(),
        broker,
    )
    del checked_runtime_spec["swap_long_per_lot"]

    with pytest.raises(
        ValueError,
        match="missing verified fields required by active notebook helpers",
    ):
        require_runtime_broker_spec(checked_runtime_spec)
