"""Verified realized and floating PnL helpers for the active engine."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .baseline import require_runtime_broker_spec
from .execution import apply_execution_price, commission_per_side


def gross_pnl(
    entry_price: float,
    exit_price: float,
    lot: float,
    direction: str,
    runtime_spec: Mapping[str, Any],
) -> float:
    """Return direction-aware gross PnL using the verified contract size."""
    spec = require_runtime_broker_spec(runtime_spec)
    numeric_entry = float(entry_price)
    numeric_exit = float(exit_price)
    numeric_lot = float(lot)
    if not all(math.isfinite(value) for value in (numeric_entry, numeric_exit, numeric_lot)):
        raise ValueError("entry_price, exit_price, and lot must be finite")
    if numeric_lot < 0.0:
        raise ValueError("lot must be non-negative")

    normalized_direction = str(direction).lower()
    if normalized_direction == "long":
        price_change = numeric_exit - numeric_entry
    elif normalized_direction == "short":
        price_change = numeric_entry - numeric_exit
    else:
        raise ValueError("direction must be 'long' or 'short'")
    return float(price_change * numeric_lot * float(spec["contract_size"]))


def mark_to_market_equity(
    cash: float,
    entry_price: float,
    lot: float,
    direction: str,
    mark_price_raw: float,
    friction: Mapping[str, Any] | None,
    runtime_spec: Mapping[str, Any],
    *,
    timestamp=None,
) -> float:
    """Return cash plus the conservative liquidation value of one position."""
    spec = require_runtime_broker_spec(runtime_spec)
    numeric_cash = float(cash)
    numeric_mark = float(mark_price_raw)
    if not math.isfinite(numeric_cash) or not math.isfinite(numeric_mark):
        raise ValueError("cash and mark_price_raw must be finite")

    normalized_direction = str(direction).lower()
    if normalized_direction == "long":
        exit_side = "sell"
    elif normalized_direction == "short":
        exit_side = "buy"
    else:
        raise ValueError("direction must be 'long' or 'short'")

    exit_price, _ = apply_execution_price(
        numeric_mark,
        exit_side,
        friction,
        spec,
        timestamp=timestamp,
    )
    floating_pnl = gross_pnl(
        entry_price,
        exit_price,
        lot,
        normalized_direction,
        spec,
    )
    exit_commission = commission_per_side(lot, friction, spec)
    return float(numeric_cash + floating_pnl - exit_commission)


def close_position(
    open_position: Mapping[str, Any],
    exit_raw: float,
    exit_reason: str,
    exit_index: int,
    exit_time,
    cash: float,
    friction: Mapping[str, Any] | None,
    runtime_spec: Mapping[str, Any],
) -> tuple[float, dict[str, Any]]:
    """Close one position and return updated realized cash plus its trade row.

    ``cash`` must already include the entry commission deduction and any swap
    booked at crossed rollover boundaries. Closing therefore realizes only
    gross price PnL less exit commission, while the trade row reports the full
    lifecycle PnL including entry commission and swap exactly once.
    """
    spec = require_runtime_broker_spec(runtime_spec)
    if not isinstance(open_position, Mapping):
        raise ValueError("open_position must be a mapping")
    required = (
        "entry_price",
        "entry_raw",
        "entry_time",
        "signal_time",
        "entry_idx",
        "entry_commission",
        "lot",
        "direction",
        "stop_loss",
        "take_profit",
    )
    missing = [field for field in required if field not in open_position]
    if missing:
        raise ValueError(f"open_position is missing required fields: {missing!r}")

    numeric_cash = float(cash)
    numeric_exit_raw = float(exit_raw)
    entry_commission = float(open_position["entry_commission"])
    swap_cash = float(open_position.get("swap_cash", 0.0))
    if not all(
        math.isfinite(value)
        for value in (numeric_cash, numeric_exit_raw, entry_commission, swap_cash)
    ):
        raise ValueError(
            "cash, exit_raw, entry_commission, and swap_cash must be finite"
        )
    if entry_commission < 0.0:
        raise ValueError("entry_commission must be non-negative")

    direction = str(open_position["direction"]).lower()
    if direction == "long":
        exit_side = "sell"
    elif direction == "short":
        exit_side = "buy"
    else:
        raise ValueError("direction must be 'long' or 'short'")

    exit_exec, _ = apply_execution_price(
        numeric_exit_raw,
        exit_side,
        friction,
        spec,
        timestamp=exit_time,
    )
    lot = float(open_position["lot"])
    exit_commission = commission_per_side(lot, friction, spec)
    gross = gross_pnl(
        open_position["entry_price"],
        exit_exec,
        lot,
        direction,
        spec,
    )
    normalized_exit_index = int(exit_index)
    entry_index = int(open_position["entry_idx"])
    bars_held = max(0, normalized_exit_index - entry_index)
    trade_pnl = gross - entry_commission - exit_commission + swap_cash
    updated_cash = float(numeric_cash + gross - exit_commission)
    trade = {
        "entry": float(open_position["entry_price"]),
        "exit": float(exit_exec),
        "entry_raw": float(open_position["entry_raw"]),
        "exit_raw": numeric_exit_raw,
        "entry_time": open_position["entry_time"],
        "exit_time": exit_time,
        "signal_time": open_position["signal_time"],
        "entry_idx": entry_index,
        "exit_idx": normalized_exit_index,
        "lot": lot,
        "direction": direction,
        "gross_pnl": float(gross),
        "entry_commission": entry_commission,
        "exit_commission": float(exit_commission),
        "swap_cash": swap_cash,
        "pnl": float(trade_pnl),
        "bars": bars_held,
        "reason": str(exit_reason),
        "stop_loss": float(open_position["stop_loss"]),
        "take_profit": float(open_position["take_profit"]),
    }
    return updated_cash, trade
