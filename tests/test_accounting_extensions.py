import json
from pathlib import Path

import pytest

from xauusd_ea.baseline import (
    entry_bid_for_short,
    exit_ask_for_short,
    load_broker_profile,
    resolve_short_exit_bid,
    risk_percent_lot,
    short_pnl_usd,
)
from xauusd_ea.reporting import build_m15_smoke_report, write_report

ROOT = Path(__file__).resolve().parents[1]


def test_short_bid_ask_execution_and_pnl():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    spread = broker.spread_price_for_multiplier(1.0)
    entry = entry_bid_for_short(2000.0)
    exit_ask = exit_ask_for_short(1999.0, spread)
    assert entry == 2000.0
    assert exit_ask == pytest.approx(1999.0 + spread)
    assert short_pnl_usd(entry, exit_ask, 1.0, broker) == pytest.approx(
        1.0 - spread
    )


def test_short_same_bar_ambiguity_is_conservatively_stop_first():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    spread = broker.spread_price_for_multiplier(1.0)
    exit_bid, reason = resolve_short_exit_bid(
        bar_open_bid=100.0 - spread,
        bar_high_bid=102.0,
        bar_low_bid=98.0 - spread,
        stop_ask=101.0,
        target_ask=99.0,
        spread_price=spread,
    )
    assert reason == "SL"
    assert exit_ask_for_short(exit_bid, spread) == pytest.approx(101.0)


def test_risk_sizing_floors_and_skips_below_minimum():
    broker = load_broker_profile(ROOT / "config" / "xm_micro_gold.json")
    assert risk_percent_lot(
        capital=1000.0,
        entry_price=2000.0,
        stop_price=1994.0,
        risk_percent=0.1,
        broker=broker,
    ) == 0.16
    assert risk_percent_lot(
        capital=1000.0,
        entry_price=2000.0,
        stop_price=1980.0,
        risk_percent=0.1,
        broker=broker,
    ) == 0.0


def test_conflicting_verified_broker_profile_fails_loudly(tmp_path):
    profile = json.loads(
        (ROOT / "config" / "xm_micro_gold.json").read_text(encoding="utf-8")
    )
    profile["contract_size"] = 100.0
    path = tmp_path / "conflict.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="conflicts"):
        load_broker_profile(path)


def test_m15_smoke_report_is_deterministic_and_persistable(tmp_path):
    first = build_m15_smoke_report(ROOT, max_rows=5000)
    second = build_m15_smoke_report(ROOT, max_rows=5000)
    assert first == second
    assert first["candidate_count"] == 3
    assert first["evaluation"] == "earliest-M15-segment; no holdout; no ranking"
    output = write_report(first, tmp_path / "report.json")
    assert output.read_text(encoding="utf-8").endswith("\n")
