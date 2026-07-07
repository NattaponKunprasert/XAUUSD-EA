from pathlib import Path

import pandas as pd
import pytest

import xauusd_ea.baseline as baseline
from xauusd_ea.baseline import (
    broker_server_rollovers_crossed,
    crossed_rollover_swap_cash,
    entry_ask_from_bid_close,
    fixed_baseline_smoke_configs,
    fixed_m15_smoke_configs,
    load_broker_profile,
    load_mt5_csv,
    mark_to_market_long_equity,
    mark_to_market_short_equity,
    normalize_baseline_timeframe,
    pnl_usd,
    resolve_long_exit_bid,
    rollover_swap_cash_from_rates,
    run_baseline_smoke,
    run_m15_baseline_smoke,
    swap_usd,
)

ROOT = Path(__file__).resolve().parents[1]


def _make_synthetic_smoke_df(
    *,
    entry_bar: dict,
    post_entry_bar: dict | None = None,
    start: str = "2023-01-03 00:00",
    periods: int = 29,
) -> pd.DataFrame:
    times = pd.date_range(start, periods=periods, freq="15min")
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


def _stub_short_baseline_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["ema_fast"] = 101.0
    out["ema_slow"] = 100.0
    out["atr_14"] = 1.0
    out.iloc[25, out.columns.get_loc("ema_fast")] = 101.0
    out.iloc[25, out.columns.get_loc("ema_slow")] = 100.0
    out.iloc[26, out.columns.get_loc("ema_fast")] = 99.0
    out.iloc[26, out.columns.get_loc("ema_slow")] = 100.0
    return out


def test_broker_profile_uses_xm_micro_gold_math():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    assert broker.symbol == "GOLDmicro"
    assert broker.contract_size == 1.0
    assert broker.tick_size == 0.01
    assert broker.tick_value_usd == 0.01
    assert broker.value_per_price_unit_per_lot == pytest.approx(1.0)
    assert broker.spread_stress_multipliers == (1.0, 1.5, 2.0)
    assert broker.commission_per_lot_round_turn_usd == 0.0


def test_spread_scenarios_are_loaded_from_broker_profile():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")

    assert broker.spread_price_for_multiplier(1.0) == pytest.approx(
        broker.spread_baseline_price
    )
    assert broker.spread_price_for_multiplier(2.0) == pytest.approx(
        broker.spread_baseline_price * 2.0
    )
    with pytest.raises(ValueError, match="Unsupported spread multiplier"):
        broker.spread_price_for_multiplier(1.25)


@pytest.mark.parametrize("timeframe", ["M15", "M30", "H1", "H4"])
def test_baseline_timeframe_normalization_accepts_supported_values(timeframe: str):
    assert normalize_baseline_timeframe(timeframe.lower()) == timeframe

    configs = fixed_baseline_smoke_configs(timeframe)
    assert [cfg["spread_multiplier"] for cfg in configs] == [1.0]
    assert all(cfg["timeframe"] == timeframe for cfg in configs)


def test_baseline_smoke_rejects_unsupported_or_mismatched_timeframes():
    with pytest.raises(ValueError, match="Unsupported baseline timeframe"):
        normalize_baseline_timeframe("D1")

    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = load_mt5_csv(ROOT / "XAUUSD_M15.csv").iloc[:500]
    config = fixed_baseline_smoke_configs("M15")[0] | {"timeframe": "H1"}
    with pytest.raises(ValueError, match="Timeframe mismatch"):
        run_baseline_smoke(df, broker, config, timeframe="M15")


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
    assert pnl_usd(
        entry_ask=2000.50, exit_bid=2001.50, lot=0.10, broker=broker
    ) == pytest.approx(0.10)


def test_mark_to_market_long_equity_uses_bid_close_and_micro_contract_size():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    position = {"entry_ask": 2000.50, "lot": 0.10}
    assert mark_to_market_long_equity(1000.0, None, 2001.50, broker) == pytest.approx(
        1000.0
    )
    assert mark_to_market_long_equity(
        1000.0, position, 2001.50, broker
    ) == pytest.approx(1000.10)


def test_mark_to_market_short_equity_uses_ask_close_and_micro_contract_size():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    position = {
        "entry_bid": 2001.50,
        "spread_price": broker.spread_baseline_price,
        "lot": 0.10,
    }
    expected_exit_ask = 2000.00 + broker.spread_baseline_price

    assert mark_to_market_short_equity(
        1000.0, None, 2000.00, broker
    ) == pytest.approx(1000.0)
    assert mark_to_market_short_equity(
        1000.0, position, 2000.00, broker
    ) == pytest.approx(1000.0 + (2001.50 - expected_exit_ask) * 0.10)


def test_swap_points_use_micro_contract_size_and_wednesday_triple():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")

    monday_rollover = pd.Timestamp("2023-01-09 00:00")
    wednesday_rollover = pd.Timestamp("2023-01-11 00:00")

    assert swap_usd(
        lot=0.10, direction="long", broker=broker, rollover_timestamp=monday_rollover
    ) == pytest.approx(-0.09339)
    assert swap_usd(
        lot=0.10, direction="short", broker=broker, rollover_timestamp=monday_rollover
    ) == pytest.approx(0.01074)
    assert swap_usd(
        lot=0.10, direction="long", broker=broker, rollover_timestamp=wednesday_rollover
    ) == pytest.approx(-0.28017)


def test_rollover_swap_cash_from_rates_matches_profile_derived_daily_values():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    short_daily_usd = broker.swap_short_points * broker.point * broker.contract_size

    assert rollover_swap_cash_from_rates(
        lot=0.10,
        direction="short",
        rollover_timestamp=pd.Timestamp("2023-01-11 00:00"),
        swap_long_per_lot_usd=(
            broker.swap_long_points * broker.point * broker.contract_size
        ),
        swap_short_per_lot_usd=short_daily_usd,
        triple_swap_day=broker.triple_swap_day,
    ) == pytest.approx(short_daily_usd * 0.10 * 3.0)


def test_crossed_rollover_swap_cash_uses_midnight_boundaries_and_skips_intraday():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    long_daily_usd = broker.swap_long_points * broker.point * broker.contract_size
    short_daily_usd = broker.swap_short_points * broker.point * broker.contract_size

    assert crossed_rollover_swap_cash(
        start=pd.Timestamp("2023-01-02 23:45"),
        end=pd.Timestamp("2023-01-03 00:15"),
        lot=0.10,
        direction="long",
        swap_long_per_lot_usd=long_daily_usd,
        swap_short_per_lot_usd=short_daily_usd,
        triple_swap_day=broker.triple_swap_day,
    ) == pytest.approx(-0.09339)
    assert crossed_rollover_swap_cash(
        start=pd.Timestamp("2023-01-03 00:00"),
        end=pd.Timestamp("2023-01-03 23:45"),
        lot=0.10,
        direction="long",
        swap_long_per_lot_usd=long_daily_usd,
        swap_short_per_lot_usd=short_daily_usd,
        triple_swap_day=broker.triple_swap_day,
    ) == pytest.approx(0.0)


def test_crossed_rollover_swap_cash_skips_weekends_and_applies_wednesday_triple():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    long_daily_usd = broker.swap_long_points * broker.point * broker.contract_size
    short_daily_usd = broker.swap_short_points * broker.point * broker.contract_size

    expected = short_daily_usd * 0.10 * 5.0
    assert crossed_rollover_swap_cash(
        start=pd.Timestamp("2023-01-10 23:45"),
        end=pd.Timestamp("2023-01-13 00:15"),
        lot=0.10,
        direction="short",
        swap_long_per_lot_usd=long_daily_usd,
        swap_short_per_lot_usd=short_daily_usd,
        triple_swap_day=broker.triple_swap_day,
    ) == pytest.approx(expected)


def test_broker_server_rollovers_crossed_uses_modeled_server_midnights():
    assert broker_server_rollovers_crossed(
        pd.Timestamp("2023-01-02 23:45"), pd.Timestamp("2023-01-03 00:00")
    ) == [pd.Timestamp("2023-01-03 00:00")]
    assert broker_server_rollovers_crossed(
        pd.Timestamp("2023-01-02 23:45"), pd.Timestamp("2023-01-03 00:15")
    ) == [pd.Timestamp("2023-01-03 00:00")]
    assert broker_server_rollovers_crossed(
        pd.Timestamp("2023-01-03 00:00"), pd.Timestamp("2023-01-03 00:15")
    ) == []


def test_broker_server_rollovers_skip_weekend_midnights():
    assert broker_server_rollovers_crossed(
        pd.Timestamp("2023-01-06 23:45"), pd.Timestamp("2023-01-09 00:00")
    ) == [pd.Timestamp("2023-01-09 00:00")]


def test_smoke_friday_to_monday_market_gap_skips_weekend_swaps(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    times = list(pd.date_range("2023-01-06 17:00", periods=28, freq="15min"))
    times.append(pd.Timestamp("2023-01-09 00:00"))
    df = pd.DataFrame(
        {
            "open": [100.0] * len(times),
            "high": [101.0] * len(times),
            "low": [100.0] * len(times),
            "close": [100.8] * len(times),
            "volume": [1.0] * len(times),
        },
        index=pd.DatetimeIndex(times),
    )
    df.iloc[28, df.columns.get_loc("open")] = 100.9
    df.iloc[28, df.columns.get_loc("high")] = 102.0
    df.iloc[28, df.columns.get_loc("low")] = 100.8
    df.iloc[28, df.columns.get_loc("close")] = 101.8
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "friday_monday_gap",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    trade = result["trades"][0]
    expected_swap = swap_usd(
        lot=0.10,
        direction="long",
        broker=broker,
        rollover_timestamp=pd.Timestamp("2023-01-09 00:00"),
    )
    assert trade["entry_time"] == pd.Timestamp("2023-01-06 23:45")
    assert trade["exit_time"] == pd.Timestamp("2023-01-09 00:00")
    assert trade["swap"] == pytest.approx(expected_swap)
    assert trade["pnl"] == pytest.approx(trade["price_pnl"] + expected_swap)
    assert result["final_capital"] == pytest.approx(1000.0 + trade["pnl"])


def test_smoke_multi_day_hold_charges_each_eligible_rollover_once(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    times = list(pd.date_range("2023-01-03 17:00", periods=28, freq="15min"))
    times.extend(
        [
            pd.Timestamp("2023-01-04 00:00"),
            pd.Timestamp("2023-01-05 00:00"),
            pd.Timestamp("2023-01-06 00:00"),
        ]
    )
    df = pd.DataFrame(
        {
            "open": [100.0] * len(times),
            "high": [101.0] * len(times),
            "low": [100.0] * len(times),
            "close": [100.8] * len(times),
            "volume": [1.0] * len(times),
        },
        index=pd.DatetimeIndex(times),
    )
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "multi_day_hold",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    charged_rollovers = broker_server_rollovers_crossed(
        pd.Timestamp("2023-01-03 23:45"), pd.Timestamp("2023-01-06 00:00")
    )
    expected_swap = sum(
        swap_usd(
            lot=0.10,
            direction="long",
            broker=broker,
            rollover_timestamp=rollover,
        )
        for rollover in charged_rollovers
    )

    assert charged_rollovers == [
        pd.Timestamp("2023-01-04 00:00"),
        pd.Timestamp("2023-01-05 00:00"),
        pd.Timestamp("2023-01-06 00:00"),
    ]
    expected_price_pnl = (
        100.8 - (100.0 + broker.spread_baseline_price)
    ) * 0.10 * broker.contract_size
    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["reason"] == "FORCED_FINAL_CLOSE"
    assert trade["swap"] == pytest.approx(expected_swap)
    assert trade["price_pnl"] == pytest.approx(expected_price_pnl)
    assert trade["pnl"] == pytest.approx(expected_price_pnl + expected_swap)
    assert result["final_capital"] == pytest.approx(1000.0 + trade["pnl"])
    assert result["equity_curve"][-1] == pytest.approx(result["final_capital"])

def test_smoke_applies_one_normal_overnight_rollover_swap(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        start="2023-01-02 17:00",
        entry_bar={"open": 100.0, "high": 101.0, "low": 100.0, "close": 100.8},
        post_entry_bar={"open": 100.9, "high": 102.0, "low": 100.8, "close": 101.8},
    )
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "normal_swap",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    trade = result["trades"][0]
    expected_swap = swap_usd(
        lot=0.10,
        direction="long",
        broker=broker,
        rollover_timestamp=pd.Timestamp("2023-01-03 00:00"),
    )
    assert trade["entry_time"] == pd.Timestamp("2023-01-02 23:45")
    assert trade["exit_time"] == pd.Timestamp("2023-01-03 00:00")
    assert trade["swap"] == pytest.approx(expected_swap)
    assert trade["pnl"] == pytest.approx(trade["price_pnl"] + expected_swap)
    assert result["final_capital"] == pytest.approx(1000.0 + trade["pnl"])
    assert result["equity_curve"][-1] == pytest.approx(result["final_capital"])


def test_short_smoke_uses_directional_swap_at_crossed_rollover(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        start="2023-01-02 17:00",
        entry_bar={"open": 100.0, "high": 100.2, "low": 99.5, "close": 99.8},
        post_entry_bar={"open": 99.8, "high": 100.0, "low": 97.0, "close": 98.0},
    )
    monkeypatch.setattr(
        baseline, "add_baseline_indicators", _stub_short_baseline_indicators
    )

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "short_normal_swap",
            "direction": "short",
            "atr_multiplier": 2.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    trade = result["trades"][0]
    expected_swap = swap_usd(
        lot=0.10,
        direction="short",
        broker=broker,
        rollover_timestamp=pd.Timestamp("2023-01-03 00:00"),
    )
    assert trade["entry_time"] == pd.Timestamp("2023-01-02 23:45")
    assert trade["exit_time"] == pd.Timestamp("2023-01-03 00:00")
    assert trade["reason"] == "TP"
    assert trade["swap"] == pytest.approx(expected_swap)
    assert trade["pnl"] == pytest.approx(trade["price_pnl"] + expected_swap)
    assert result["final_capital"] == pytest.approx(1000.0 + trade["pnl"])


def test_smoke_applies_wednesday_triple_rollover_swap(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        start="2023-01-03 17:00",
        entry_bar={"open": 100.0, "high": 101.0, "low": 100.0, "close": 100.8},
        post_entry_bar={"open": 100.9, "high": 102.0, "low": 100.8, "close": 101.8},
    )
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "triple_swap",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    trade = result["trades"][0]
    assert trade["entry_time"] == pd.Timestamp("2023-01-03 23:45")
    assert trade["exit_time"] == pd.Timestamp("2023-01-04 00:00")
    assert trade["swap"] == pytest.approx(-0.28017)
    assert trade["pnl"] == pytest.approx(trade["price_pnl"] + trade["swap"])
    assert result["final_capital"] == pytest.approx(1000.0 + trade["pnl"])


def test_smoke_does_not_apply_swap_without_crossed_rollover(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        start="2023-01-02 16:00",
        entry_bar={"open": 100.0, "high": 101.0, "low": 100.0, "close": 100.8},
        post_entry_bar={"open": 100.9, "high": 102.0, "low": 100.8, "close": 101.8},
    )
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "no_swap",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    trade = result["trades"][0]
    assert trade["entry_time"] == pd.Timestamp("2023-01-02 22:45")
    assert trade["exit_time"] == pd.Timestamp("2023-01-02 23:00")
    assert trade["swap"] == pytest.approx(0.0)
    assert trade["pnl"] == pytest.approx(trade["price_pnl"])
    assert result["final_capital"] == pytest.approx(1000.0 + trade["pnl"])


def test_open_smoke_position_books_swap_once_in_cash_and_equity(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        start="2023-01-02 17:00",
        periods=30,
        entry_bar={"open": 100.0, "high": 101.0, "low": 100.0, "close": 100.8},
        post_entry_bar={"open": 100.9, "high": 101.0, "low": 100.8, "close": 101.0},
    )
    df.iloc[29, df.columns.get_loc("open")] = 101.0
    df.iloc[29, df.columns.get_loc("high")] = 101.2
    df.iloc[29, df.columns.get_loc("low")] = 100.9
    df.iloc[29, df.columns.get_loc("close")] = 101.1
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "open_swap_once",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    expected_swap = -0.09339
    entry_ask = 100.0 + broker.spread_baseline_price
    expected_price_pnl = (101.1 - entry_ask) * 0.10 * broker.contract_size
    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["reason"] == "FORCED_FINAL_CLOSE"
    assert trade["swap"] == pytest.approx(expected_swap)
    assert trade["price_pnl"] == pytest.approx(expected_price_pnl)
    assert result["final_capital"] == pytest.approx(1000.0 + trade["pnl"])
    assert result["equity_curve"][-1] == pytest.approx(result["final_capital"])


def test_forced_final_close_realizes_last_bid_close_without_extra_swap(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        start="2023-01-02 16:00",
        periods=29,
        entry_bar={"open": 100.0, "high": 100.7, "low": 100.0, "close": 100.6},
        post_entry_bar={"open": 100.8, "high": 100.9, "low": 100.7, "close": 100.9},
    )
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "forced_final_close",
            "atr_multiplier": 2.0,
            "rr": 2.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    trade = result["trades"][0]
    expected_exit_bid = 100.9
    expected_entry_ask = 100.0 + broker.spread_baseline_price
    expected_price_pnl = (
        expected_exit_bid - expected_entry_ask
    ) * 0.10 * broker.contract_size

    assert result["trade_count"] == 1
    assert trade["entry_time"] == pd.Timestamp("2023-01-02 22:45")
    assert trade["exit_time"] == pd.Timestamp("2023-01-02 23:00")
    assert trade["reason"] == "FORCED_FINAL_CLOSE"
    assert trade["swap"] == pytest.approx(0.0)
    assert trade["exit_bid"] == pytest.approx(expected_exit_bid)
    assert trade["price_pnl"] == pytest.approx(expected_price_pnl)
    assert result["final_capital"] == pytest.approx(1000.0 + expected_price_pnl)
    assert result["equity_curve"][-1] == pytest.approx(result["final_capital"])

def test_m15_only_fixed_smoke_executes_closed_trades_without_full_grid():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = load_mt5_csv(ROOT / "XAUUSD_M15.csv").iloc[:5000]
    result = run_m15_baseline_smoke(df, broker, fixed_m15_smoke_configs()[0])
    assert set(result) == {"trades", "final_capital", "trade_count", "equity_curve"}
    assert result["trade_count"] == 3
    assert [trade["reason"] for trade in result["trades"]] == ["TP", "SL", "SL"]
    assert result["final_capital"] == pytest.approx(999.6668571428571)
    assert result["final_capital"] == pytest.approx(
        1000.0 + sum(t["pnl"] for t in result["trades"])
    )
    assert result["equity_curve"][-1] == pytest.approx(result["final_capital"])


def test_fixed_m15_smoke_configs_cover_configured_spread_scenarios():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    configs = fixed_m15_smoke_configs(broker)

    assert [cfg["spread_multiplier"] for cfg in configs] == [1.0, 1.5, 2.0]
    assert all(cfg["max_trades"] == 3 for cfg in configs)
    assert all(cfg["timeframe"] == "M15" for cfg in configs)


def test_stress_spread_changes_ask_entry_and_open_equity(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        entry_bar={"open": 100.0, "high": 101.0, "low": 100.0, "close": 100.80},
        post_entry_bar={"open": 100.90, "high": 101.20, "low": 100.80, "close": 101.00},
    )
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)
    baseline_result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "baseline_spread_open_equity",
            "atr_multiplier": 2.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
            "spread_multiplier": 1.0,
        },
    )
    stress_result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "stress_spread_open_equity",
            "atr_multiplier": 2.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
            "spread_multiplier": 2.0,
        },
    )

    extra_spread = broker.spread_baseline_price
    assert baseline_result["trade_count"] == 1
    assert stress_result["trade_count"] == 1
    assert stress_result["trades"][0]["reason"] == "FORCED_FINAL_CLOSE"
    assert baseline_result["trades"][0]["reason"] == "FORCED_FINAL_CLOSE"
    assert stress_result["final_capital"] == pytest.approx(
        baseline_result["final_capital"]
        - extra_spread * 0.10 * broker.contract_size
    )
    assert stress_result["equity_curve"][-1] == pytest.approx(
        stress_result["final_capital"]
    )


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


def test_short_smoke_executes_next_bar_bid_entry_and_ask_target(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        entry_bar={"open": 100.0, "high": 100.2, "low": 98.0, "close": 99.0}
    )
    monkeypatch.setattr(
        baseline, "add_baseline_indicators", _stub_short_baseline_indicators
    )

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "short_entry_bar_tp",
            "direction": "short",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["direction"] == "short"
    assert trade["signal_time"] == df.index[26]
    assert trade["entry_time"] == trade["exit_time"] == df.index[27]
    assert trade["entry_bid"] == pytest.approx(df.iloc[27]["open"])
    assert trade["reason"] == "TP"
    assert trade["exit_ask"] == pytest.approx(trade["target_ask"])
    assert trade["price_pnl"] == pytest.approx(0.10)
    assert result["final_capital"] == pytest.approx(1000.10)
    assert result["equity_curve"][-1] == pytest.approx(result["final_capital"])


def test_short_smoke_same_bar_ambiguity_resolves_to_ask_stop(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        entry_bar={"open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0}
    )
    monkeypatch.setattr(
        baseline, "add_baseline_indicators", _stub_short_baseline_indicators
    )

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "short_entry_bar_conflict",
            "direction": "short",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    trade = result["trades"][0]
    assert trade["entry_time"] == trade["exit_time"] == df.index[27]
    assert trade["reason"] == "SL"
    assert trade["exit_ask"] == pytest.approx(trade["stop_ask"])
    assert trade["price_pnl"] == pytest.approx(-0.10)


def test_short_smoke_forced_close_and_equity_mark_use_ask(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        entry_bar={"open": 100.0, "high": 100.2, "low": 99.5, "close": 99.8},
        post_entry_bar={
            "open": 99.8,
            "high": 100.0,
            "low": 99.4,
            "close": 99.6,
        },
    )
    monkeypatch.setattr(
        baseline, "add_baseline_indicators", _stub_short_baseline_indicators
    )

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "short_forced_close",
            "direction": "short",
            "atr_multiplier": 2.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    trade = result["trades"][0]
    expected_exit_ask = 99.6 + broker.spread_baseline_price
    expected_price_pnl = (100.0 - expected_exit_ask) * 0.10
    assert trade["reason"] == "FORCED_FINAL_CLOSE"
    assert trade["exit_bid"] == pytest.approx(99.6)
    assert trade["exit_ask"] == pytest.approx(expected_exit_ask)
    assert trade["price_pnl"] == pytest.approx(expected_price_pnl)
    assert result["final_capital"] == pytest.approx(1000.0 + expected_price_pnl)
    assert result["equity_curve"][-1] == pytest.approx(result["final_capital"])


def test_smoke_rejects_unknown_direction():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = load_mt5_csv(ROOT / "XAUUSD_M15.csv").iloc[:100]
    config = fixed_m15_smoke_configs()[0] | {"direction": "both"}

    with pytest.raises(ValueError, match="direction must be"):
        run_m15_baseline_smoke(df, broker, config)


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
    df = _make_synthetic_smoke_df(
        entry_bar={"open": 100.0, "high": 102.0, "low": 100.0, "close": 101.0}
    )
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "entry_bar_tp",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["entry_time"] == trade["exit_time"] == df.index[27]
    assert trade["reason"] == "TP"
    assert trade["exit_bid"] == pytest.approx(trade["target_bid"])


def test_smoke_trade_uses_gap_open_when_bar_opens_below_stop(
    monkeypatch: pytest.MonkeyPatch,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = _make_synthetic_smoke_df(
        entry_bar={"open": 100.0, "high": 101.0, "low": 100.0, "close": 100.5},
        post_entry_bar={"open": 99.0, "high": 99.2, "low": 98.8, "close": 99.1},
    )
    monkeypatch.setattr(baseline, "add_baseline_indicators", _stub_baseline_indicators)

    result = run_m15_baseline_smoke(
        df,
        broker,
        {
            "name": "gap_stop",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
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
        {
            "name": "open_equity",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 1,
        },
    )

    assert result["trade_count"] == 1
    assert result["trades"][0]["reason"] == "FORCED_FINAL_CLOSE"
    assert len(result["equity_curve"]) == 2
    assert result["equity_curve"][0] == pytest.approx(
        1000.0
        + (100.80 - (100.0 + broker.spread_baseline_price))
        * 0.10
        * broker.contract_size
    )
    assert result["final_capital"] == pytest.approx(
        1000.0
        + (101.00 - (100.0 + broker.spread_baseline_price))
        * 0.10
        * broker.contract_size
    )
    assert result["equity_curve"][-1] == pytest.approx(
        result["final_capital"]
    )


@pytest.mark.parametrize(
    ("timeframe", "filename", "expected_reasons", "expected_final_capital"),
    [
        ("M30", "XAUUSD_M30.csv", ["TP", "SL", "SL"], 999.6055442857142),
        ("H1", "XAUUSD_H1.csv", ["TP", "TP", "TP"], 1001.3821428571428),
        ("H4", "XAUUSD_H4.csv", ["SL", "TP", "TP"], 1000.4074999999999),
    ],
)
def test_higher_timeframe_smoke_paths_match_deterministic_baselines(
    timeframe: str,
    filename: str,
    expected_reasons: list[str],
    expected_final_capital: float,
):
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    df = load_mt5_csv(ROOT / filename).iloc[:5000]

    result = run_baseline_smoke(
        df,
        broker,
        fixed_baseline_smoke_configs(timeframe)[0],
        timeframe=timeframe,
    )

    assert set(result) == {"trades", "final_capital", "trade_count", "equity_curve"}
    assert result["trade_count"] == 3
    assert [trade["reason"] for trade in result["trades"]] == expected_reasons
    assert all(trade["timeframe"] == timeframe for trade in result["trades"])
    assert result["final_capital"] == pytest.approx(expected_final_capital)
    assert result["final_capital"] == pytest.approx(
        1000.0 + sum(trade["pnl"] for trade in result["trades"])
    )
    assert result["equity_curve"][-1] == pytest.approx(result["final_capital"])
