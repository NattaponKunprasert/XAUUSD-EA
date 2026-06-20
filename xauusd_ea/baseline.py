"""M15-only baseline smoke-test utilities for XM Micro GOLDmicro.

This module is intentionally small and deterministic.  It does not run or
materialize the notebook optimization grid; it only exercises broker math and a
fixed M15 backtest path that can be audited before strategy logic is changed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import pandas as pd


REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class BrokerProfile:
    symbol: str
    contract_size: float
    tick_size: float
    tick_value_usd: float
    point: float
    spread_baseline_price: float
    commission_per_lot_round_turn_usd: float
    fee_per_lot_round_turn_usd: float
    min_lot: float
    max_lot: float
    lot_step: float
    initial_capital_usd: float

    @property
    def value_per_price_unit_per_lot(self) -> float:
        return self.tick_value_usd / self.tick_size

    def quantize_lot(self, raw_lot: float) -> float:
        if raw_lot <= 0:
            return 0.0
        steps = round((raw_lot - self.min_lot) / self.lot_step)
        lot = self.min_lot + steps * self.lot_step
        lot = max(self.min_lot, min(self.max_lot, lot))
        return round(lot, 2)


def load_broker_profile(path: str | Path) -> BrokerProfile:
    with Path(path).open("r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    return BrokerProfile(
        symbol=cfg["symbol"],
        contract_size=float(cfg["contract_size"]),
        tick_size=float(cfg["tick_size"]),
        tick_value_usd=float(cfg["tick_value_usd"]),
        point=float(cfg["point"]),
        spread_baseline_price=float(cfg["spread_baseline_price"]),
        commission_per_lot_round_turn_usd=float(cfg["commission_per_lot_round_turn_usd"]),
        fee_per_lot_round_turn_usd=float(cfg["fee_per_lot_round_turn_usd"]),
        min_lot=float(cfg["min_lot"]),
        max_lot=float(cfg["max_lot"]),
        lot_step=float(cfg["lot_step"]),
        initial_capital_usd=float(cfg["initial_capital_usd"]),
    )


def load_mt5_csv(filepath: str | Path) -> pd.DataFrame:
    """Load the intentional mixed-delimiter MT5 OHLCV export format."""
    raw = pd.read_csv(filepath, sep=r"[\t,;|]", engine="python")
    raw.columns = [str(c).strip().replace("<", "").replace(">", "") for c in raw.columns]
    rename = {c: c.lower() for c in raw.columns}
    df = raw.rename(columns=rename)
    if "time" not in df.columns:
        raise ValueError(f"Missing Time column in {filepath}")
    df["time"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M", errors="coerce")
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"Missing required column {col!r} in {filepath}")
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=("time", *REQUIRED_COLUMNS)).drop_duplicates("time").sort_values("time")
    return df.set_index("time")


def add_baseline_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = out["close"].ewm(span=12, adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=26, adjust=False).mean()
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [out["high"] - out["low"], (out["high"] - prev_close).abs(), (out["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    out["atr_14"] = tr.rolling(14).mean()
    return out


def entry_ask_from_bid_close(bid_close: float, spread_price: float) -> float:
    return bid_close + spread_price


def exit_bid_for_long(bid_price: float) -> float:
    return bid_price


def pnl_usd(entry_ask: float, exit_bid: float, lot: float, broker: BrokerProfile) -> float:
    gross = (exit_bid - entry_ask) * lot * broker.contract_size
    return gross - broker.commission_per_lot_round_turn_usd * lot - broker.fee_per_lot_round_turn_usd * lot


def fixed_m15_smoke_configs() -> list[dict]:
    """Tiny fixed configuration set; not an optimization grid."""
    return [
        {"name": "ema12_26_atr_rr1", "atr_multiplier": 1.0, "rr": 1.0, "lot": 0.10, "max_trades": 3},
    ]


def run_m15_baseline_smoke(df: pd.DataFrame, broker: BrokerProfile, config: dict) -> dict:
    """Run one deterministic long-only smoke path using Bid OHLC and Ask entries.

    The function purposely uses one position at a time, fixed lot, no swap, no
    historical news filter, and no parameter search.
    """
    data = add_baseline_indicators(df)
    capital = broker.initial_capital_usd
    trades: list[dict] = []
    position = None

    for i in range(27, len(data)):
        row = data.iloc[i]
        prev = data.iloc[i - 1]
        if position is None:
            crossed_up = prev["ema_fast"] <= prev["ema_slow"] and row["ema_fast"] > row["ema_slow"]
            if not crossed_up or pd.isna(row["atr_14"]):
                continue
            entry_ask = entry_ask_from_bid_close(row["close"], broker.spread_baseline_price)
            risk_distance = row["atr_14"] * config["atr_multiplier"]
            position = {
                "entry_time": row.name,
                "entry_ask": entry_ask,
                "stop_bid": entry_ask - risk_distance,
                "target_bid": entry_ask + risk_distance * config["rr"],
                "lot": broker.quantize_lot(config["lot"]),
            }
            continue

        exit_reason = None
        exit_bid = None
        if row["low"] <= position["stop_bid"]:
            exit_bid = position["stop_bid"]
            exit_reason = "SL"
        elif row["high"] >= position["target_bid"]:
            exit_bid = position["target_bid"]
            exit_reason = "TP"

        if exit_reason:
            trade_pnl = pnl_usd(position["entry_ask"], exit_bid, position["lot"], broker)
            capital += trade_pnl
            trades.append({**position, "exit_time": row.name, "exit_bid": exit_bid, "reason": exit_reason, "pnl": trade_pnl})
            position = None
            if len(trades) >= config["max_trades"]:
                break

    return {"trades": trades, "final_capital": capital, "trade_count": len(trades)}
