"""Minimal immutable runtime primitives for synthetic H1 D2 only.

This module intentionally has no research, selection, CSV, or baseline-smoke
path.  It is the small, separately attestable subset of broker/execution math
required by the Round-3 volatility-shock D2 worker.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BrokerProfile:
    symbol: str
    aliases: tuple[str, ...]
    digits: int
    contract_size: float
    tick_size: float
    tick_value_usd: float
    point: float
    ohlc_price_source: str
    spread_mode: str
    spread_baseline_price: float
    spread_stress_multipliers: tuple[float, ...]
    commission_per_lot_round_turn_usd: float
    fee_per_lot_round_turn_usd: float
    min_lot: float
    max_lot: float
    lot_step: float
    execution: str
    account_mode: str
    initial_capital_usd: float
    swap_type: str
    swap_long_points: float
    swap_short_points: float
    triple_swap_day: str

    def quantize_lot(self, raw_lot: float) -> float:
        if raw_lot < self.min_lot:
            return 0.0
        capped = min(raw_lot, self.max_lot)
        steps = int((capped - self.min_lot) / self.lot_step + 1e-12)
        return round(self.min_lot + steps * self.lot_step, 2)

    def spread_price_for_multiplier(self, multiplier: float) -> float:
        if multiplier not in self.spread_stress_multipliers:
            raise ValueError("Unsupported spread multiplier")
        return self.spread_baseline_price * multiplier


def load_broker_profile_snapshot(snapshot: bytes) -> BrokerProfile:
    if type(snapshot) is not bytes:
        raise ValueError("Broker profile snapshot must be exact immutable bytes")
    try:
        cfg = json.loads(snapshot.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Broker profile snapshot is not valid UTF-8 JSON") from exc
    if not isinstance(cfg, dict):
        raise ValueError("Broker profile snapshot must decode to a JSON object")
    verified = {"profile_id": "xm_micro_gold", "symbol": "GOLDmicro",
                "ohlc_price_source": "bid", "contract_size": 1.0,
                "commission_per_lot_round_turn_usd": 0.0,
                "fee_per_lot_round_turn_usd": 0.0, "swap_type": "points",
                "triple_swap_day": "Wednesday"}
    if any(cfg.get(key) != value for key, value in verified.items()):
        raise ValueError("Broker profile conflicts with verified XM Micro constants")
    try:
        return BrokerProfile(
            symbol=cfg["symbol"], aliases=tuple(str(x) for x in cfg.get("aliases", ())),
            digits=int(cfg["digits"]), contract_size=float(cfg["contract_size"]),
            tick_size=float(cfg["tick_size"]), tick_value_usd=float(cfg["tick_value_usd"]),
            point=float(cfg["point"]), ohlc_price_source=str(cfg["ohlc_price_source"]),
            spread_mode=str(cfg["spread_mode"]), spread_baseline_price=float(cfg["spread_baseline_price"]),
            spread_stress_multipliers=tuple(float(x) for x in cfg["spread_stress_multipliers"]),
            commission_per_lot_round_turn_usd=float(cfg["commission_per_lot_round_turn_usd"]),
            fee_per_lot_round_turn_usd=float(cfg["fee_per_lot_round_turn_usd"]),
            min_lot=float(cfg["min_lot"]), max_lot=float(cfg["max_lot"]), lot_step=float(cfg["lot_step"]),
            execution=str(cfg["execution"]), account_mode=str(cfg["account_mode"]),
            initial_capital_usd=float(cfg["initial_capital_usd"]), swap_type=str(cfg["swap_type"]),
            swap_long_points=float(cfg["swap_long_points_snapshot"]),
            swap_short_points=float(cfg["swap_short_points_snapshot"]), triple_swap_day=str(cfg["triple_swap_day"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Broker profile snapshot has invalid schema") from exc


def add_baseline_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    prev_close = out["close"].shift(1)
    tr = pd.concat([out["high"] - out["low"], (out["high"] - prev_close).abs(),
                    (out["low"] - prev_close).abs()], axis=1).max(axis=1)
    out["atr_14"] = tr.rolling(14).mean()
    return out


def entry_ask_from_bid_close(bid_close: float, spread_price: float) -> float: return bid_close + spread_price
def entry_bid_for_short(bid_price: float) -> float: return float(bid_price)
def exit_ask_for_short(bid_price: float, spread_price: float) -> float: return float(bid_price) + float(spread_price)


def pnl_usd(entry_ask: float, exit_bid: float, lot: float, broker: BrokerProfile) -> float:
    return (exit_bid - entry_ask) * lot * broker.contract_size - broker.commission_per_lot_round_turn_usd * lot - broker.fee_per_lot_round_turn_usd * lot


def short_pnl_usd(entry_bid: float, exit_ask: float, lot: float, broker: BrokerProfile) -> float:
    return (entry_bid - exit_ask) * lot * broker.contract_size - broker.commission_per_lot_round_turn_usd * lot - broker.fee_per_lot_round_turn_usd * lot


def mark_to_market_long_equity(cash: float, position: dict | None, mark_bid: float, broker: BrokerProfile) -> float:
    return float(cash) if position is None else float(cash + pnl_usd(position["entry_ask"], mark_bid, position["lot"], broker))


def mark_to_market_short_equity(cash: float, position: dict | None, mark_ask: float, broker: BrokerProfile) -> float:
    return float(cash) if position is None else float(cash + short_pnl_usd(position["entry_bid"], mark_ask, position["lot"], broker))


def resolve_long_exit_bid(*, bar_open_bid: float, bar_high_bid: float, bar_low_bid: float, stop_bid: float, target_bid: float) -> tuple[float | None, str | None]:
    if bar_open_bid <= stop_bid: return bar_open_bid, "SL"
    if bar_open_bid >= target_bid: return bar_open_bid, "TP"
    if bar_low_bid <= stop_bid: return stop_bid, "SL"
    if bar_high_bid >= target_bid: return target_bid, "TP"
    return None, None


def resolve_short_exit_bid(*, bar_open_bid: float, bar_high_bid: float, bar_low_bid: float, stop_ask: float, target_ask: float, spread_price: float) -> tuple[float | None, str | None]:
    open_ask, high_ask, low_ask = bar_open_bid + spread_price, bar_high_bid + spread_price, bar_low_bid + spread_price
    if open_ask >= stop_ask: return float(bar_open_bid), "SL"
    if open_ask <= target_ask: return float(bar_open_bid), "TP"
    if high_ask >= stop_ask: return float(stop_ask - spread_price), "SL"
    if low_ask <= target_ask: return float(target_ask - spread_price), "TP"
    return None, None


def _swap_usd(*, lot: float, direction: str, broker: BrokerProfile, rollover_timestamp: pd.Timestamp) -> float:
    if broker.swap_type != "points" or direction not in {"long", "short"}:
        raise ValueError("Unsupported swap profile or direction")
    points = broker.swap_long_points if direction == "long" else broker.swap_short_points
    return points * broker.point * lot * broker.contract_size * (3 if rollover_timestamp.day_name() == broker.triple_swap_day else 1)


def _rollovers_crossed(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if end <= start: return []
    cursor, result = start.normalize() + pd.offsets.Day(1), []
    while cursor <= end:
        if cursor.day_name() not in {"Saturday", "Sunday"}: result.append(cursor)
        cursor += pd.offsets.Day(1)
    return result


def apply_crossed_rollover_swaps(*, cash: float, position: dict, current_time: pd.Timestamp, broker: BrokerProfile) -> float:
    total = sum(_swap_usd(lot=position["lot"], direction=position["direction"], broker=broker, rollover_timestamp=item) for item in _rollovers_crossed(position.get("last_swap_check_time", position["entry_time"]), current_time))
    if total:
        position["swap"] += total
        cash += total
    position["last_swap_check_time"] = pd.Timestamp(current_time)
    return cash


def _validated_directional_risk_levels(*, direction: str, entry_price: float, signal_atr: float, atr_multiplier: float, rr: float) -> tuple[float, float]:
    try:
        risk, reward = signal_atr * atr_multiplier, signal_atr * atr_multiplier * rr
        stop, target = (entry_price - risk, entry_price + reward) if direction == "long" else (entry_price + risk, entry_price - reward) if direction == "short" else (_ for _ in ()).throw(ValueError())
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError("Directional runtime risk level arithmetic is invalid") from exc
    if not all(math.isfinite(x) for x in (entry_price, risk, reward, stop, target)) or risk <= 0 or reward <= 0 or not (stop < entry_price < target if direction == "long" else target < entry_price < stop):
        raise ValueError("Directional runtime risk levels are not finite and strictly ordered")
    return float(stop), float(target)
