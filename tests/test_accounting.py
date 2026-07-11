from pathlib import Path

import pytest

from xauusd_ea.accounting import gross_pnl
from xauusd_ea.baseline import (
    assert_runtime_broker_spec_matches_profile,
    load_broker_profile,
)


ROOT = Path(__file__).resolve().parents[1]


def _runtime_spec() -> dict:
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    return assert_runtime_broker_spec_matches_profile(broker.to_runtime_spec(), broker)


def test_gross_pnl_uses_verified_micro_contract_for_long_and_short():
    spec = _runtime_spec()

    assert gross_pnl(2000.0, 2006.0, 0.25, "long", spec) == pytest.approx(1.5)
    assert gross_pnl(2000.0, 1994.0, 0.25, "short", spec) == pytest.approx(1.5)


def test_gross_pnl_preserves_losses_and_zero_volume():
    spec = _runtime_spec()

    assert gross_pnl(2000.0, 1994.0, 0.25, "long", spec) == pytest.approx(-1.5)
    assert gross_pnl(2000.0, 1994.0, 0.0, "long", spec) == 0.0


@pytest.mark.parametrize("direction", ["buy", "sell", "mystery"])
def test_gross_pnl_rejects_non_position_directions(direction):
    with pytest.raises(ValueError, match="direction must be"):
        gross_pnl(2000.0, 2001.0, 0.1, direction, _runtime_spec())


def test_gross_pnl_rejects_invalid_values_and_unverified_contract_override():
    spec = _runtime_spec()
    with pytest.raises(ValueError, match="must be finite"):
        gross_pnl(2000.0, float("nan"), 0.1, "long", spec)
    with pytest.raises(ValueError, match="non-negative"):
        gross_pnl(2000.0, 2001.0, -0.1, "long", spec)

    conflicting = dict(spec)
    conflicting["contract_size"] = 100.0
    with pytest.raises(ValueError, match="no longer matches"):
        gross_pnl(2000.0, 2001.0, 0.1, "long", conflicting)
