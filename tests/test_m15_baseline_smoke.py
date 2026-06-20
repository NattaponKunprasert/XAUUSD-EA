from pathlib import Path

import pytest

from xauusd_ea.baseline import (
    entry_ask_from_bid_close,
    fixed_m15_smoke_configs,
    load_broker_profile,
    load_mt5_csv,
    pnl_usd,
    run_m15_baseline_smoke,
)

ROOT = Path(__file__).resolve().parents[1]


def test_broker_profile_uses_xm_micro_gold_math():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    assert broker.symbol == "GOLDmicro"
    assert broker.contract_size == 1.0
    assert broker.tick_size == 0.01
    assert broker.tick_value_usd == 0.01
    assert broker.value_per_price_unit_per_lot == pytest.approx(1.0)
    assert broker.commission_per_lot_round_turn_usd == 0.0


def test_bid_ask_entry_and_contract_size_pnl_math():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    entry_ask = entry_ask_from_bid_close(2000.00, broker.spread_baseline_price)
    assert entry_ask == pytest.approx(2000.5511428571428)
    assert pnl_usd(entry_ask=2000.50, exit_bid=2001.50, lot=0.10, broker=broker) == pytest.approx(0.10)


def test_m15_only_fixed_smoke_completes_without_full_grid():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = load_mt5_csv(ROOT / "XAUUSD_M15.csv").iloc[:5000]
    result = run_m15_baseline_smoke(df, broker, fixed_m15_smoke_configs()[0])
    assert set(result) == {"trades", "final_capital", "trade_count"}
    assert result["trade_count"] <= 3
    assert result["final_capital"] == pytest.approx(1000.0 + sum(t["pnl"] for t in result["trades"]))
