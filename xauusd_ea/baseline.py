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
    spread_stress_multipliers: tuple[float, ...]
    commission_per_lot_round_turn_usd: float
    fee_per_lot_round_turn_usd: float
    min_lot: float
    max_lot: float
    lot_step: float
    initial_capital_usd: float
    swap_type: str
    swap_long_points: float
    swap_short_points: float
    triple_swap_day: str

    @property
    def value_per_price_unit_per_lot(self) -> float:
        return self.tick_value_usd / self.tick_size

    def quantize_lot(self, raw_lot: float) -> float:
        """Risk-safe lot quantization for XM Micro volumes.

        Never increase requested risk: values below the broker minimum return 0,
        values above the maximum are capped, and valid values are floored to the
        nearest lot step rather than rounded upward.
        """
        if raw_lot < self.min_lot:
            return 0.0
        capped = min(raw_lot, self.max_lot)
        steps = int((capped - self.min_lot) / self.lot_step + 1e-12)
        lot = self.min_lot + steps * self.lot_step
        return round(lot, 2)

    def spread_price_for_multiplier(self, multiplier: float) -> float:
        if multiplier not in self.spread_stress_multipliers:
            raise ValueError(
                f"Unsupported spread multiplier {multiplier!r}; expected one of "
                f"{self.spread_stress_multipliers!r}"
            )
        return self.spread_baseline_price * multiplier


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
        spread_stress_multipliers=tuple(
            float(multiplier) for multiplier in cfg["spread_stress_multipliers"]
        ),
        commission_per_lot_round_turn_usd=float(
            cfg["commission_per_lot_round_turn_usd"]
        ),
        fee_per_lot_round_turn_usd=float(cfg["fee_per_lot_round_turn_usd"]),
        min_lot=float(cfg["min_lot"]),
        max_lot=float(cfg["max_lot"]),
        lot_step=float(cfg["lot_step"]),
        initial_capital_usd=float(cfg["initial_capital_usd"]),
        swap_type=str(cfg["swap_type"]),
        swap_long_points=float(cfg["swap_long_points_snapshot"]),
        swap_short_points=float(cfg["swap_short_points_snapshot"]),
        triple_swap_day=str(cfg["triple_swap_day"]),
    )


def load_mt5_csv(filepath: str | Path) -> pd.DataFrame:
    """Load the intentional mixed-delimiter MT5 OHLCV export format."""
    raw = pd.read_csv(filepath, sep=r"[\t,;|]", engine="python")
    raw.columns = [
        str(c).strip().replace("<", "").replace(">", "") for c in raw.columns
    ]
    rename = {c: c.lower() for c in raw.columns}
    df = raw.rename(columns=rename)
    if "time" not in df.columns:
        raise ValueError(f"Missing Time column in {filepath}")
    df["time"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M", errors="coerce")
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"Missing required column {col!r} in {filepath}")
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = (
        df.dropna(subset=("time", *REQUIRED_COLUMNS))
        .drop_duplicates("time")
        .sort_values("time")
    )
    return df.set_index("time")


def add_baseline_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = out["close"].ewm(span=12, adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=26, adjust=False).mean()
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr_14"] = tr.rolling(14).mean()
    return out


def entry_ask_from_bid_close(bid_close: float, spread_price: float) -> float:
    return bid_close + spread_price


def exit_bid_for_long(bid_price: float) -> float:
    return bid_price


def pnl_usd(
    entry_ask: float, exit_bid: float, lot: float, broker: BrokerProfile
) -> float:
    gross = (exit_bid - entry_ask) * lot * broker.contract_size
    return (
        gross
        - broker.commission_per_lot_round_turn_usd * lot
        - broker.fee_per_lot_round_turn_usd * lot
    )


def mark_to_market_long_equity(
    cash: float, position: dict | None, mark_bid: float, broker: BrokerProfile
) -> float:
    """Account equity as cash plus open long PnL marked to a Bid price.

    ``cash`` already includes any swap booked at crossed broker-server
    rollover boundaries.  Open equity therefore adds only the current floating
    price PnL, avoiding a second swap application while the position remains
    open.
    """
    if position is None:
        return float(cash)
    return float(
        cash + pnl_usd(position["entry_ask"], mark_bid, position["lot"], broker)
    )


def resolve_long_exit_bid(
    *,
    bar_open_bid: float,
    bar_high_bid: float,
    bar_low_bid: float,
    stop_bid: float,
    target_bid: float,
) -> tuple[float | None, str | None]:
    """Resolve a long exit on Bid OHLC using a conservative intrabar policy.

    Gap-at-open handling is explicit:
    - if the bar opens through the stop, exit at the open Bid
    - if the bar opens through the target, exit at the open Bid
    - if both stop and target are reached later within the same bar, prefer SL
    """
    if bar_open_bid <= stop_bid:
        return bar_open_bid, "SL"
    if bar_open_bid >= target_bid:
        return bar_open_bid, "TP"

    stop_hit = bar_low_bid <= stop_bid
    target_hit = bar_high_bid >= target_bid
    if stop_hit:
        return stop_bid, "SL"
    if target_hit:
        return target_bid, "TP"
    return None, None


def swap_usd(
    *,
    lot: float,
    direction: str,
    broker: BrokerProfile,
    rollover_timestamp: pd.Timestamp,
) -> float:
    """Return the XM Micro overnight swap charge/credit for one rollover.

    The verified broker snapshot stores swap as points.  For GOLDmicro one
    point is 0.01 price units and one lot has contract size 1, so the USD
    value is points * point * lot * contract_size.  The configured Wednesday
    rollover is charged at three times the normal daily amount.
    """
    if broker.swap_type != "points":
        raise ValueError(
            f"Unsupported swap_type {broker.swap_type!r}; expected 'points'"
        )
    if direction not in {"long", "short"}:
        raise ValueError(
            f"Unsupported direction {direction!r}; expected 'long' or 'short'"
        )

    swap_points = (
        broker.swap_long_points if direction == "long" else broker.swap_short_points
    )
    multiplier = 3 if rollover_timestamp.day_name() == broker.triple_swap_day else 1
    return swap_points * broker.point * lot * broker.contract_size * multiplier



def broker_server_rollovers_crossed(
    start: pd.Timestamp, end: pd.Timestamp
) -> list[pd.Timestamp]:
    """Return modeled server-midnight swap rollovers crossed in ``(start, end]``.

    This baseline models rollover at midnight in the CSV/MT5 server-clock
    timestamp domain.  The exact broker rollover cutover time is a backtest
    modeling assumption until it is explicitly verified or configured.  Weekend
    midnights are skipped because the configured Wednesday triple swap covers
    the weekend carry.
    """
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if end <= start:
        return []

    next_rollover = start.normalize() + pd.Timedelta(days=1)
    rollovers: list[pd.Timestamp] = []
    while next_rollover <= end:
        if next_rollover.day_name() not in {"Saturday", "Sunday"}:
            rollovers.append(next_rollover)
        next_rollover += pd.Timedelta(days=1)
    return rollovers


def apply_crossed_rollover_swaps(
    *,
    cash: float,
    position: dict,
    current_time: pd.Timestamp,
    broker: BrokerProfile,
) -> float:
    """Book each newly crossed broker-server rollover exactly once."""
    last_checked = position.get("last_swap_check_time", position["entry_time"])
    swap_total = 0.0
    for rollover in broker_server_rollovers_crossed(last_checked, current_time):
        swap_total += swap_usd(
            lot=position["lot"],
            direction="long",
            broker=broker,
            rollover_timestamp=rollover,
        )
    if swap_total:
        position["swap"] += swap_total
        cash += swap_total
    position["last_swap_check_time"] = pd.Timestamp(current_time)
    return cash


def fixed_m15_smoke_configs(broker: BrokerProfile | None = None) -> list[dict]:
    """Tiny fixed configuration set; not an optimization grid."""
    spread_multipliers = broker.spread_stress_multipliers if broker else (1.0,)
    return [
        {
            "name": f"ema12_26_atr_rr1_spread_{spread_multiplier:g}x",
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 3,
            "spread_multiplier": spread_multiplier,
        }
        for spread_multiplier in spread_multipliers
    ]


def run_m15_baseline_smoke(
    df: pd.DataFrame, broker: BrokerProfile, config: dict
) -> dict:
    """Run one deterministic long-only smoke path using Bid OHLC and Ask entries.

    The function purposely uses one position at a time, fixed lot, broker-server
    midnight rollover swap accounting, no historical news filter, and no
    parameter search.
    """
    data = add_baseline_indicators(df)
    capital = broker.initial_capital_usd
    equity_curve: list[float] = []
    trades: list[dict] = []
    position = None
    spread_multiplier = float(config.get("spread_multiplier", 1.0))
    spread_price = broker.spread_price_for_multiplier(spread_multiplier)

    for i in range(27, len(data)):
        row = data.iloc[i]
        prev = data.iloc[i - 1]
        if position is None:
            signal_bar = prev
            signal_prev = data.iloc[i - 2]
            crossed_up = (
                signal_prev["ema_fast"] <= signal_prev["ema_slow"]
                and signal_bar["ema_fast"] > signal_bar["ema_slow"]
            )
            if crossed_up and not pd.isna(signal_bar["atr_14"]):
                lot = broker.quantize_lot(config["lot"])
                if lot != 0.0:
                    entry_ask = entry_ask_from_bid_close(row["open"], spread_price)
                    risk_distance = signal_bar["atr_14"] * config["atr_multiplier"]
                    position = {
                        "signal_time": signal_bar.name,
                        "entry_time": row.name,
                        "entry_ask": entry_ask,
                        "entry_bid_open": row["open"],
                        "spread_price": spread_price,
                        "spread_multiplier": spread_multiplier,
                        "stop_bid": entry_ask - risk_distance,
                        "target_bid": entry_ask + risk_distance * config["rr"],
                        "lot": lot,
                        "swap": 0.0,
                        "last_swap_check_time": row.name,
                    }

        if position is not None:
            capital = apply_crossed_rollover_swaps(
                cash=capital,
                position=position,
                current_time=row.name,
                broker=broker,
            )
            exit_bid, exit_reason = resolve_long_exit_bid(
                bar_open_bid=row["open"],
                bar_high_bid=row["high"],
                bar_low_bid=row["low"],
                stop_bid=position["stop_bid"],
                target_bid=position["target_bid"],
            )
            if exit_reason:
                price_pnl = pnl_usd(
                    position["entry_ask"], exit_bid, position["lot"], broker
                )
                trade_pnl = price_pnl + position["swap"]
                capital += price_pnl
                trades.append(
                    {
                        **position,
                        "exit_time": row.name,
                        "exit_bid": exit_bid,
                        "reason": exit_reason,
                        "price_pnl": price_pnl,
                        "swap": position["swap"],
                        "pnl": trade_pnl,
                    }
                )
                position = None

        equity_curve.append(
            mark_to_market_long_equity(capital, position, row["close"], broker)
        )
        if len(trades) >= config["max_trades"]:
            break

    return {
        "trades": trades,
        "final_capital": capital,
        "trade_count": len(trades),
        "equity_curve": equity_curve,
    }
