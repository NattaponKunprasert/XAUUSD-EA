"""Verified position-sizing helpers for the active research engine."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .baseline import merge_runtime_broker_overrides, require_runtime_broker_spec


def calculate_position_size(
    capital: float,
    entry_price: float,
    stop_loss_price: float,
    sizing_method: str = "fixed",
    config: Mapping[str, Any] | None = None,
    *,
    runtime_spec: Mapping[str, Any],
    **kwargs: Any,
) -> float:
    """Calculate and risk-safely floor a volume against the verified broker spec.

    Risk-percent sizing uses the price distance to the frozen stop. ATR sizing
    uses the already-frozen ATR value supplied by the caller. Any positive raw
    size below the broker minimum is a no-trade instead of being rounded up.
    """
    spec = require_runtime_broker_spec(runtime_spec)
    overrides = config if config is not None else kwargs
    cfg = merge_runtime_broker_overrides(
        spec,
        overrides,
        context="calculate_position_size",
    )

    method = str(sizing_method)
    if method == "fixed":
        raw_lot = cfg.get("fixed_lot", 1.0)
    elif method == "risk_percent":
        distance = abs(float(entry_price) - float(stop_loss_price))
        risk_cash = float(capital) * float(cfg.get("risk_percent", 1.0)) / 100.0
        if not math.isfinite(distance) or distance <= 0.0:
            return 0.0
        if not math.isfinite(risk_cash) or risk_cash <= 0.0:
            return 0.0
        raw_lot = risk_cash / (distance * float(cfg["contract_size"]))
    elif method == "atr_based":
        volatility_divider = cfg.get("volatility_divider")
        if volatility_divider is not None:
            volatility_factor = float(volatility_divider)
        elif cfg.get("atr") is not None:
            volatility_factor = float(cfg["atr"]) * float(
                cfg.get("atr_multiplier", 1.0)
            )
        else:
            return 0.0
        if not math.isfinite(volatility_factor) or volatility_factor <= 0.0:
            return 0.0
        raw_lot = float(cfg.get("base_lot_size", 0.1)) / volatility_factor
    else:
        raise ValueError(f"Invalid sizing method: {sizing_method}")

    try:
        raw_lot = float(raw_lot)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(raw_lot) or raw_lot <= 0.0:
        return 0.0

    min_lot = float(cfg["min_lot"])
    max_lot = float(cfg["max_lot"])
    lot_step = float(cfg["lot_step"])
    if lot_step <= 0.0:
        raise ValueError("lot_step must be positive")
    if raw_lot < min_lot:
        return 0.0

    capped_lot = min(raw_lot, max_lot)
    steps = int((capped_lot - min_lot) / lot_step + 1e-12)
    floored_lot = min_lot + steps * lot_step
    precision = int(cfg.get("precision", spec.get("lot_precision", 2)))
    return min(max_lot, round(floored_lot, precision))
