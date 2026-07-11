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
