from pathlib import Path

import pandas as pd
import pytest

import xauusd_ea.baseline as baseline
from xauusd_ea.baseline import (
    entry_ask_from_bid_close,
    fixed_m15_smoke_configs,
    load_broker_profile,
    load_mt5_csv,
    mark_to_market_long_equity,
    pnl_usd,
    resolve_long_exit_bid,
    run_m15_baseline_smoke,
)

ROOT = Path(__file__).resolve().parents[1]


def _make_synthetic_smoke_df(*, entry_bar: dict, post_entry_bar: dict | None = None) -> pd.DataFrame:
    times = pd.date_range("2023-01-03 00:00", periods=29, freq="15min")
    df = pd.DataFrame(
        {
            "open": [100.0] * len(times),
            "high": [100.2] * len(times),
            "low": [99.8] * len(times),
            "close": [100.0] * len(times),
            "volume": [1.0] * len(times),
        },
        index=times,
    )
    for key, value in entry_bar.items():
        df.loc[times[27], key] = value
    if post_entry_bar is not None:
        for key, value in post_entry_bar.items():
            df.loc[times[28], key] = value
    return df


def _stub_baseline_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["ema_fast"] = 99.0
    out["ema_slow"] = 100.0
    out["atr_14"] = 1.0
    out.iloc[25, out.columns.get_loc("ema_fast")] = 99.0
    out.iloc[25, out.columns.get_loc("ema_slow")] = 100.0
    out.iloc[26, out.columns.get_loc("ema_fast")] = 101.0
    out.iloc[26, out.columns.get_loc("ema_slow")] = 100.0
    out.iloc[26, out.columns.get_loc("atr_14")] = 1.0
    return out


def test_broker_profile_uses_xm_micro_gold_math():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    assert broker.symbol == "GOLDmicro"
    assert broker.contract_size == 1.0
    assert broker.tick_size == 0.01
    assert broker.tick_value_usd == 0.01
    assert broker.value_per_price_unit_per_lot == pytest.approx(1.0)
    assert broker.commission_per_lot_round_turn_usd == 0.0


def test_quantize_lot_never_exceeds_requested_raw_lot():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    assert broker.quantize_lot(0.099) == 0.0
    assert broker.quantize_lot(0.10) == 0.10
    assert broker.quantize_lot(0.109) == 0.10
    assert broker.quantize_lot(0.119) == 0.11
    assert broker.quantize_lot(100.50) == 100.0
    for raw in [0.101, 0.109, 0.111, 1.239, 99.999]:
        assert broker.quantize_lot(raw) <= raw


def test_bid_ask_entry_and_contract_size_pnl_math():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    entry_ask = entry_ask_from_bid_close(2000.00, broker.spread_baseline_price)
    assert entry_ask == pytest.approx(2000.5511428571428)
    assert pnl_usd(entry_ask=2000.50, exit_bid=2001.50, lot=0.10, broker=broker) == pytest.approx(0.10)


def test_mark_to_market_long_equity_uses_bid_close_and_micro_contract_size():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    position = {"entry_ask": 2000.50, "lot": 0.10}
    assert mark_to_market_long_equity(1000.0, None, 2001.50, broker) == pytest.approx(1000.0)
    assert mark_to_market_long_equity(1000.0, position, 2001.50, broker) == pytest.approx(1000.10)


def test_m15_only_fixed_smoke_executes_closed_trades_without_full_grid():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = load_mt5_csv(ROOT / "XAUUSD_M15.csv").iloc[:5000]
    result = run_m15_baseline_smoke(df, broker, fixed_m15_smoke_configs()[0])
    assert set(result) == {"trades", "final_capital", "trade_count", "equity_curve"}
    assert result["trade_count"] == 3
    assert [trade["reason"] for trade in result["trades"]] == ["TP", "SL", "SL"]
    assert result["final_capital"] == pytest.approx(999.6668571428571)
    assert result["final_capital"] == pytest.approx(1000.0 + sum(t["pnl"] for t in result["trades"]))
    assert result["equity_curve"][-1] == pytest.approx(result["final_capital"])


def test_smoke_entries_execute_on_next_bar_open_plus_spread():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = load_mt5_csv(ROOT / "XAUUSD_M15.csv").iloc[:5000]
    result = run_m15_baseline_smoke(df, broker, fixed_m15_smoke_configs()[0])
    first = result["trades"][0]
    assert first["signal_time"].isoformat() == "2023-01-03T16:15:00"
    assert first["entry_time"].isoformat() == "2023-01-03T16:30:00"
    assert first["entry_time"] > first["signal_time"]
    expected_entry_ask = first["entry_bid_open"] + broker.spread_baseline_price
    assert first["entry_ask"] == pytest.approx(expected_entry_ask)
    assert first["entry_ask"] == pytest.approx(1841.6311428571428)


def test_resolve_long_exit_bid_is_gap_aware_and_conservative():
    exit_bid, reason = resolve_long_exit_bid(
        bar_open_bid=97.50,
        bar_high_bid=99.50,
        bar_low_bid=97.00,
        stop_bid=98.50,
        target_bid=101.50,
    )
    assert reason == "SL"
    assert exit_bid == pytest.approx(97.50)

    exit_bid, reason = resolve_long_exit_bid(
        bar_open_bid=100.00,
        bar_high_bid=102.00,
        bar_low_bid=98.00,
        stop_bid=98.50,
        target_bid=101.50,
    )
    assert reason == "SL"
    assert exit_bid == pytest.approx(98.50)


def test_smoke_trade_can_exit_on_entry_bar(monkeypatch: pytest.MonkeyPatch):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(entry_bar={"open": 100.0, "high": 102.0, "low": 100.0, "close": 101.0})
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {"name": "entry_bar_tp", "atr_multiplier": 1.0, "rr": 1.0, "lot": 0.10, "max_trades": 1},
    )

    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["entry_time"] == trade["exit_time"] == df.index[27]
    assert trade["reason"] == "TP"
    assert trade["exit_bid"] == pytest.approx(trade["target_bid"])


def test_smoke_trade_uses_gap_open_when_bar_opens_below_stop(monkeypatch: pytest.MonkeyPatch):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        entry_bar={"open": 100.0, "high": 101.0, "low": 100.0, "close": 100.5},
        post_entry_bar={"open": 99.0, "high": 99.2, "low": 98.8, "close": 99.1},
    )
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {"name": "gap_stop", "atr_multiplier": 1.0, "rr": 1.0, "lot": 0.10, "max_trades": 1},
    )

    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["entry_time"] == df.index[27]
    assert trade["exit_time"] == df.index[28]
    assert trade["reason"] == "SL"
    assert trade["stop_bid"] > trade["exit_bid"]
    assert trade["exit_bid"] == pytest.approx(99.0)


def test_smoke_equity_marks_open_position_to_bid_close(monkeypatch: pytest.MonkeyPatch):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        entry_bar={"open": 100.0, "high": 101.0, "low": 100.0, "close": 100.80},
        post_entry_bar={"open": 100.90, "high": 101.20, "low": 100.80, "close": 101.00},
    )
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {"name": "open_equity", "atr_multiplier": 1.0, "rr": 1.0, "lot": 0.10, "max_trades": 1},
    )

    assert result["trade_count"] == 0
    assert result["final_capital"] == pytest.approx(1000.0)
    assert len(result["equity_curve"]) == 2
    assert result["equity_curve"][0] == pytest.approx(
        1000.0 + (100.80 - (100.0 + broker.spread_baseline_price)) * 0.10 * broker.contract_size
    )
    assert result["equity_curve"][-1] == pytest.approx(
        1000.0 + (101.00 - (100.0 + broker.spread_baseline_price)) * 0.10 * broker.contract_size
    )
