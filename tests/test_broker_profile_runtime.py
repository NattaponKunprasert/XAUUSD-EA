from pathlib import Path

import pytest

from xauusd_ea.baseline import (
    assert_runtime_broker_spec_matches_profile,
    load_broker_profile,
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
    }

    merged = assert_runtime_broker_spec_matches_profile(runtime_spec, broker)

    assert merged["symbol"] == "GOLDmicro"
    assert merged["lot_precision"] == 2
    assert merged["spread_application"] == "full"


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


def test_runtime_spec_match_rejects_missing_required_verified_fields():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    incomplete_spec = {
        "symbol": "GOLDmicro",
        "contract_size": 1.0,
    }

    with pytest.raises(ValueError, match="digits: missing; expected 2"):
        assert_runtime_broker_spec_matches_profile(incomplete_spec, broker)
