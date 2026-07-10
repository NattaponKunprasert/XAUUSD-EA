"""Verified execution-price and commission helpers for the active engine."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from .baseline import merge_runtime_broker_overrides, require_runtime_broker_spec


SUPPORTED_SLIPPAGE_MODES = frozenset(
    {"fixed", "random_normal", "random_uniform", "time_sensitive"}
)


def to_price_units(
    value: float,
    runtime_spec: Mapping[str, Any],
    friction: Mapping[str, Any] | None = None,
) -> float:
    """Convert an audited point-denominated cost to price units."""
    spec = require_runtime_broker_spec(runtime_spec)
    merged = merge_runtime_broker_overrides(
        spec,
        friction,
        context="to_price_units",
        allow_supported_spread_override=True,
    )
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError("cost value must be finite")

    mode = str(merged["cost_value_mode"]).lower()
    if mode == "points":
        return numeric_value * float(spec["point"])
    if mode == "price":
        return numeric_value
    raise ValueError("cost_value_mode must be 'points' or 'price'")


def spread_price(
    friction: Mapping[str, Any] | None,
    runtime_spec: Mapping[str, Any],
) -> float:
    """Return the configured audited spread in price units."""
    spec = require_runtime_broker_spec(runtime_spec)
    merged = merge_runtime_broker_overrides(
        spec,
        friction,
        context="spread_price",
        allow_supported_spread_override=True,
    )
    return abs(to_price_units(merged["spread_points"], spec, merged))


def apply_execution_price(
    price: float,
    side: str,
    friction: Mapping[str, Any] | None,
    runtime_spec: Mapping[str, Any],
    *,
    timestamp=None,
    rng=None,
) -> tuple[float, dict[str, float | str]]:
    """Convert raw OHLC into a Bid/Ask-aware executable price.

    The verified CSV source is Bid. A buy therefore pays the full spread while
    a sell starts from Bid. Slippage is adverse for both sides.
    """
    spec = require_runtime_broker_spec(runtime_spec)
    merged = merge_runtime_broker_overrides(
        spec,
        friction,
        context="apply_execution_price",
        allow_supported_spread_override=True,
    )

    numeric_price = float(price)
    if not math.isfinite(numeric_price):
        raise ValueError("price must be finite")
    normalized_side = str(side).lower()
    if normalized_side not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")

    slippage_mode = str(merged.get("slippage_mode", "fixed")).lower()
    if slippage_mode not in SUPPORTED_SLIPPAGE_MODES:
        raise ValueError(
            f"unsupported slippage_mode {slippage_mode!r}; expected one of "
            f"{sorted(SUPPORTED_SLIPPAGE_MODES)!r}"
        )
    slippage_value = float(merged.get("slippage_value", 0.0))
    active_rng = rng if rng is not None else np.random

    if slippage_mode == "fixed":
        raw_slippage = slippage_value
    elif slippage_mode == "random_normal":
        raw_slippage = active_rng.normal(
            float(merged.get("slippage_mu", slippage_value)),
            float(merged.get("slippage_sigma", 0.0)),
        )
    elif slippage_mode == "random_uniform":
        raw_slippage = active_rng.uniform(
            float(merged.get("slippage_low", 0.0)),
            float(merged.get("slippage_high", slippage_value)),
        )
    else:
        hour = pd.Timestamp(timestamp).hour if timestamp is not None else 12
        raw_slippage = slippage_value * 2.0 if 8 <= hour <= 17 else slippage_value

    slippage = abs(to_price_units(raw_slippage, spec, merged))
    spread = spread_price(merged, spec)
    source = str(spec["ohlc_price_source"]).lower()

    if source == "bid":
        spread_component = spread if normalized_side == "buy" else 0.0
    elif source == "ask":
        spread_component = spread if normalized_side == "sell" else 0.0
    elif source == "mid":
        spread_component = (
            spread / 2.0 if spec.get("spread_application", "half") == "half" else spread
        )
    else:
        raise ValueError("ohlc_price_source must be 'bid', 'ask', or 'mid'")

    adjustment = spread_component + slippage
    executed = (
        numeric_price + adjustment
        if normalized_side == "buy"
        else numeric_price - adjustment
    )
    return float(executed), {
        "slippage": float(slippage),
        "spread_component": float(spread_component),
        "spread_total": float(spread),
        "ohlc_price_source": source,
    }


def commission_per_side(
    lot: float,
    friction: Mapping[str, Any] | None,
    runtime_spec: Mapping[str, Any],
) -> float:
    """Return one side of the verified round-turn commission."""
    spec = require_runtime_broker_spec(runtime_spec)
    merged = merge_runtime_broker_overrides(
        spec,
        friction,
        context="commission_per_side",
        allow_supported_spread_override=True,
    )
    numeric_lot = float(lot)
    if not math.isfinite(numeric_lot) or numeric_lot < 0.0:
        raise ValueError("lot must be finite and non-negative")
    return numeric_lot * float(merged["commission_per_lot_round_turn"]) / 2.0
