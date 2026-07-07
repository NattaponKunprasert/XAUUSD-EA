"""Deterministic baseline smoke-test utilities for XM Micro GOLDmicro.

This module is intentionally small and deterministic.  It does not run or
materialize the notebook optimization grid; it only exercises broker math and a
fixed backtest path that can be audited before strategy logic is changed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import pandas as pd

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")
SUPPORTED_BASELINE_TIMEFRAMES = ("M15", "M30", "H1", "H4")
REQUIRED_RUNTIME_BROKER_SPEC_FIELDS = (
    "symbol",
    "contract_size",
    "point",
    "min_lot",
    "max_lot",
    "lot_step",
    "spread_points",
    "commission_per_lot_round_turn",
    "fee_per_lot_round_turn",
    "swap_per_lot",
    "swap_long_per_lot",
    "swap_short_per_lot",
    "cost_value_mode",
)
VERIFIED_RUNTIME_SPEC_FINGERPRINT_FIELD = "verified_runtime_spec_fingerprint"
DEFAULT_BROKER_PROFILE_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "xm_micro_gold.json"
)
VERIFIED_RUNTIME_SPEC_FINGERPRINT_KEYS = (
    "symbol",
    "aliases",
    "digits",
    "contract_size",
    "tick_size",
    "tick_value_usd",
    "point",
    "ohlc_price_source",
    "spread_mode",
    "spread_baseline_price",
    "spread_stress_multipliers",
    "commission_per_lot_round_turn_usd",
    "fee_per_lot_round_turn_usd",
    "min_lot",
    "max_lot",
    "lot_step",
    "execution",
    "account_mode",
    "initial_capital_usd",
    "swap_type",
    "swap_long_points",
    "swap_short_points",
    "triple_swap_day",
    "cost_value_mode",
    "spread_points",
    "commission_per_lot_round_turn",
    "fee_per_lot_round_turn",
    "swap_per_lot",
    "swap_long_per_lot",
    "swap_short_per_lot",
)
RUNTIME_SPEC_SPREAD_OVERRIDE_FIELD = "spread_points"
RUNTIME_SPEC_SPREAD_TOLERANCE = 1e-9


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

    @property
    def value_per_price_unit_per_lot(self) -> float:
        return self.tick_value_usd / self.tick_size

    @property
    def lot_precision(self) -> int:
        text = f"{self.lot_step:.12f}".rstrip("0")
        return len(text.partition(".")[2])

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

    def spread(self, multiplier: float = 1.0) -> float:
        return self.spread_price_for_multiplier(float(multiplier))

    def executable_price(
        self, bid_price: float, side: str, spread_multiplier: float = 1.0
    ) -> float:
        """Convert verified Bid OHLC into an executable Bid/Ask price."""
        if self.ohlc_price_source != "bid":
            raise ValueError("baseline execution requires Bid OHLC")
        side = str(side).lower()
        if side == "buy":
            return float(bid_price) + self.spread(spread_multiplier)
        if side == "sell":
            return float(bid_price)
        raise ValueError("side must be 'buy' or 'sell'")

    def to_runtime_spec(self) -> dict[str, Any]:
        """Return the verified broker constants for runtime/backtest paths."""
        return {
            "symbol": self.symbol,
            "aliases": list(self.aliases),
            "digits": self.digits,
            "contract_size": self.contract_size,
            "tick_size": self.tick_size,
            "tick_value_usd": self.tick_value_usd,
            "point": self.point,
            "ohlc_price_source": self.ohlc_price_source,
            "spread_mode": self.spread_mode,
            "spread_baseline_price": self.spread_baseline_price,
            "spread_stress_multipliers": list(self.spread_stress_multipliers),
            "commission_per_lot_round_turn_usd": (
                self.commission_per_lot_round_turn_usd
            ),
            "fee_per_lot_round_turn_usd": self.fee_per_lot_round_turn_usd,
            "min_lot": self.min_lot,
            "max_lot": self.max_lot,
            "lot_step": self.lot_step,
            "execution": self.execution,
            "account_mode": self.account_mode,
            "initial_capital_usd": self.initial_capital_usd,
            "swap_type": self.swap_type,
            "swap_long_points": self.swap_long_points,
            "swap_short_points": self.swap_short_points,
            "triple_swap_day": self.triple_swap_day,
        }


def load_broker_profile(path: str | Path) -> BrokerProfile:
    with Path(path).open("r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    verified = {
        "profile_id": "xm_micro_gold",
        "symbol": "GOLDmicro",
        "ohlc_price_source": "bid",
        "contract_size": 1.0,
        "commission_per_lot_round_turn_usd": 0.0,
        "fee_per_lot_round_turn_usd": 0.0,
        "swap_type": "points",
        "triple_swap_day": "Wednesday",
    }
    conflicts = {
        key: (cfg.get(key), expected)
        for key, expected in verified.items()
        if cfg.get(key) != expected
    }
    if conflicts:
        raise ValueError(
            f"Broker profile conflicts with verified XM Micro constants: {conflicts}"
        )
    return BrokerProfile(
        symbol=cfg["symbol"],
        aliases=tuple(str(alias) for alias in cfg.get("aliases", ())),
        digits=int(cfg["digits"]),
        contract_size=float(cfg["contract_size"]),
        tick_size=float(cfg["tick_size"]),
        tick_value_usd=float(cfg["tick_value_usd"]),
        point=float(cfg["point"]),
        ohlc_price_source=str(cfg["ohlc_price_source"]),
        spread_mode=str(cfg["spread_mode"]),
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
        execution=str(cfg["execution"]),
        account_mode=str(cfg["account_mode"]),
        initial_capital_usd=float(cfg["initial_capital_usd"]),
        swap_type=str(cfg["swap_type"]),
        swap_long_points=float(cfg["swap_long_points_snapshot"]),
        swap_short_points=float(cfg["swap_short_points_snapshot"]),
        triple_swap_day=str(cfg["triple_swap_day"]),
    )


def assert_runtime_broker_spec_matches_profile(
    runtime_spec: Mapping[str, Any],
    broker: BrokerProfile,
) -> dict[str, Any]:
    """Fail loudly when an active runtime spec conflicts with the verified config."""
    expected = broker.to_runtime_spec()
    derived_expectations = _runtime_spec_derived_expectations(broker)
    comparable_fields = (
        "symbol",
        "aliases",
        "digits",
        "contract_size",
        "tick_size",
        "tick_value_usd",
        "point",
        "ohlc_price_source",
        "spread_mode",
        "spread_baseline_price",
        "spread_stress_multipliers",
        "commission_per_lot_round_turn_usd",
        "fee_per_lot_round_turn_usd",
        "min_lot",
        "max_lot",
        "lot_step",
        "execution",
        "account_mode",
        "initial_capital_usd",
        "swap_type",
        "swap_long_points",
        "swap_short_points",
        "triple_swap_day",
    )
    mismatches: list[str] = []
    for field in comparable_fields:
        if field not in runtime_spec:
            mismatches.append(f"{field}: missing; expected {expected[field]!r}")
            continue
        actual = runtime_spec[field]
        wanted = expected[field]
        if actual != wanted:
            mismatches.append(f"{field}: got {actual!r}, expected {wanted!r}")
    for field, wanted in derived_expectations.items():
        if field not in runtime_spec:
            continue
        actual = runtime_spec[field]
        if actual != wanted:
            mismatches.append(f"{field}: got {actual!r}, expected {wanted!r}")

    if mismatches:
        joined = "; ".join(mismatches)
        raise ValueError(
            "Runtime broker spec conflicts with config/xm_micro_gold.json: "
            f"{joined}"
        )

    merged = dict(expected)
    merged.update(derived_expectations)
    merged.update(runtime_spec)
    merged[VERIFIED_RUNTIME_SPEC_FINGERPRINT_FIELD] = (
        _verified_runtime_spec_fingerprint(merged)
    )
    return merged


def require_runtime_broker_spec(
    runtime_spec: Mapping[str, Any] | None,
    *,
    required_fields: tuple[str, ...] = REQUIRED_RUNTIME_BROKER_SPEC_FIELDS,
    broker_profile_path: str | Path = DEFAULT_BROKER_PROFILE_PATH,
) -> dict[str, Any]:
    """Require a verified runtime broker spec before notebook helpers execute."""
    if runtime_spec is None:
        raise ValueError(
            "Runtime broker spec is not initialized; load and verify "
            "config/xm_micro_gold.json before running notebook helpers"
        )
    if not isinstance(runtime_spec, Mapping):
        raise ValueError(
            "Runtime broker spec must be a mapping loaded from "
            "config/xm_micro_gold.json"
        )
    missing = [field for field in required_fields if field not in runtime_spec]
    if missing:
        raise ValueError(
            "Runtime broker spec is missing verified fields required by active "
            f"notebook helpers: {missing!r}"
        )
    fingerprint = runtime_spec.get(VERIFIED_RUNTIME_SPEC_FINGERPRINT_FIELD)
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ValueError(
            "Runtime broker spec is missing its verified profile fingerprint; "
            "load and verify config/xm_micro_gold.json before running notebook "
            "helpers"
        )

    normalized = dict(runtime_spec)
    broker = load_broker_profile(broker_profile_path)
    try:
        verified_runtime_spec = assert_runtime_broker_spec_matches_profile(
            normalized, broker
        )
    except ValueError as exc:
        raise ValueError(
            "Runtime broker spec no longer matches the verified "
            "config/xm_micro_gold.json snapshot; reload and re-verify the "
            "broker profile before running notebook helpers"
        ) from exc
    expected_fingerprint = verified_runtime_spec[VERIFIED_RUNTIME_SPEC_FINGERPRINT_FIELD]
    if fingerprint != expected_fingerprint:
        raise ValueError(
            "Runtime broker spec no longer matches the verified "
            "config/xm_micro_gold.json snapshot; reload and re-verify the "
            "broker profile before running notebook helpers"
        )
    return verified_runtime_spec


def merge_runtime_broker_overrides(
    runtime_spec: Mapping[str, Any] | None,
    overrides: Mapping[str, Any] | None,
    *,
    context: str,
    allow_supported_spread_override: bool = False,
) -> dict[str, Any]:
    """Merge non-broker overrides while rejecting conflicting broker constants."""
    verified_runtime_spec = require_runtime_broker_spec(runtime_spec)
    if overrides is None:
        return dict(verified_runtime_spec)
    if not isinstance(overrides, Mapping):
        raise ValueError(f"{context} overrides must be a mapping")

    merged = dict(verified_runtime_spec)
    conflicts: list[str] = []
    for key, value in overrides.items():
        if key not in verified_runtime_spec:
            merged[key] = value
            continue
        if (
            allow_supported_spread_override
            and key == RUNTIME_SPEC_SPREAD_OVERRIDE_FIELD
            and value != verified_runtime_spec[key]
        ):
            merged[key] = _validated_supported_spread_override(
                value=value,
                runtime_spec=verified_runtime_spec,
                context=context,
            )
            continue
        if value != verified_runtime_spec[key]:
            conflicts.append(
                f"{key}: got {value!r}, expected {verified_runtime_spec[key]!r}"
            )
            continue
        merged[key] = value

    if conflicts:
        raise ValueError(
            f"{context} conflicts with the verified runtime broker spec: "
            + "; ".join(conflicts)
        )
    return merged


def _verified_runtime_spec_fingerprint(runtime_spec: Mapping[str, Any]) -> str:
    payload = {
        field: runtime_spec[field]
        for field in VERIFIED_RUNTIME_SPEC_FINGERPRINT_KEYS
        if field in runtime_spec
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return encoded


def _runtime_spec_derived_expectations(broker: BrokerProfile) -> dict[str, Any]:
    return {
        "cost_value_mode": "points",
        "spread_points": broker.spread_baseline_price / broker.point,
        "commission_per_lot_round_turn": broker.commission_per_lot_round_turn_usd,
        "fee_per_lot_round_turn": broker.fee_per_lot_round_turn_usd,
        "swap_per_lot": broker.swap_long_points * broker.point * broker.contract_size,
        "swap_long_per_lot": (
            broker.swap_long_points * broker.point * broker.contract_size
        ),
        "swap_short_per_lot": (
            broker.swap_short_points * broker.point * broker.contract_size
        ),
    }


def _validated_supported_spread_override(
    *,
    value: Any,
    runtime_spec: Mapping[str, Any],
    context: str,
) -> float:
    try:
        candidate = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{context} spread override must be numeric, got {value!r}"
        ) from exc

    baseline_points = float(runtime_spec["spread_baseline_price"]) / float(
        runtime_spec["point"]
    )
    for multiplier in runtime_spec["spread_stress_multipliers"]:
        allowed = baseline_points * float(multiplier)
        if abs(candidate - allowed) <= RUNTIME_SPEC_SPREAD_TOLERANCE:
            return allowed

    raise ValueError(
        f"{context} spread_points override {candidate!r} is not one of the "
        "audited baseline/stress spreads from config/xm_micro_gold.json"
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


def normalize_baseline_timeframe(timeframe: str) -> str:
    normalized = str(timeframe).upper()
    if normalized not in SUPPORTED_BASELINE_TIMEFRAMES:
        raise ValueError(
            f"Unsupported baseline timeframe {timeframe!r}; expected one of "
            f"{SUPPORTED_BASELINE_TIMEFRAMES!r}"
        )
    return normalized


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


def entry_bid_for_short(bid_price: float) -> float:
    return float(bid_price)


def exit_bid_for_long(bid_price: float) -> float:
    return bid_price


def exit_ask_for_short(bid_price: float, spread_price: float) -> float:
    return float(bid_price) + float(spread_price)


def pnl_usd(
    entry_ask: float, exit_bid: float, lot: float, broker: BrokerProfile
) -> float:
    gross = (exit_bid - entry_ask) * lot * broker.contract_size
    return (
        gross
        - broker.commission_per_lot_round_turn_usd * lot
        - broker.fee_per_lot_round_turn_usd * lot
    )


def short_pnl_usd(
    entry_bid: float,
    exit_ask: float,
    lot: float,
    broker: BrokerProfile,
) -> float:
    gross = (entry_bid - exit_ask) * lot * broker.contract_size
    return (
        gross
        - broker.commission_per_lot_round_turn_usd * lot
        - broker.fee_per_lot_round_turn_usd * lot
    )


def risk_percent_lot(
    *,
    capital: float,
    entry_price: float,
    stop_price: float,
    risk_percent: float,
    broker: BrokerProfile,
) -> float:
    """Floor risk sizing to the broker step; never round up below min lot."""
    distance = abs(float(entry_price) - float(stop_price))
    if capital <= 0 or distance <= 0 or risk_percent <= 0:
        return 0.0
    risk_cash = float(capital) * float(risk_percent) / 100.0
    raw_lot = risk_cash / (distance * broker.value_per_price_unit_per_lot)
    return broker.quantize_lot(raw_lot)


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


def mark_to_market_short_equity(
    cash: float,
    position: dict | None,
    mark_bid: float,
    broker: BrokerProfile,
) -> float:
    """Account equity as cash plus open short PnL marked to the current Ask."""
    if position is None:
        return float(cash)
    mark_ask = exit_ask_for_short(mark_bid, position["spread_price"])
    return float(
        cash + short_pnl_usd(position["entry_bid"], mark_ask, position["lot"], broker)
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


def resolve_short_exit_bid(
    *,
    bar_open_bid: float,
    bar_high_bid: float,
    bar_low_bid: float,
    stop_ask: float,
    target_ask: float,
    spread_price: float,
) -> tuple[float | None, str | None]:
    """Resolve a short exit using Ask triggers derived from Bid OHLC."""
    open_ask = bar_open_bid + spread_price
    high_ask = bar_high_bid + spread_price
    low_ask = bar_low_bid + spread_price
    if open_ask >= stop_ask:
        return float(bar_open_bid), "SL"
    if open_ask <= target_ask:
        return float(bar_open_bid), "TP"
    stop_hit = high_ask >= stop_ask
    target_hit = low_ask <= target_ask
    if stop_hit:
        return float(stop_ask - spread_price), "SL"
    if target_hit:
        return float(target_ask - spread_price), "TP"
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


def rollover_swap_cash_from_rates(
    *,
    lot: float,
    direction: str,
    rollover_timestamp: pd.Timestamp,
    swap_long_per_lot_usd: float,
    swap_short_per_lot_usd: float,
    triple_swap_day: str,
) -> float:
    """Return one crossed-rollover swap cash amount from per-lot USD rates."""
    if direction not in {"long", "short"}:
        raise ValueError(
            f"Unsupported direction {direction!r}; expected 'long' or 'short'"
        )
    daily_swap = (
        float(swap_long_per_lot_usd)
        if direction == "long"
        else float(swap_short_per_lot_usd)
    )
    multiplier = (
        3 if pd.Timestamp(rollover_timestamp).day_name() == triple_swap_day else 1
    )
    return float(lot) * daily_swap * multiplier


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

    next_rollover = start.normalize() + pd.offsets.Day(1)
    rollovers: list[pd.Timestamp] = []
    while next_rollover <= end:
        if next_rollover.day_name() not in {"Saturday", "Sunday"}:
            rollovers.append(next_rollover)
        next_rollover += pd.offsets.Day(1)
    return rollovers


def crossed_rollover_swap_cash(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    lot: float,
    direction: str,
    swap_long_per_lot_usd: float,
    swap_short_per_lot_usd: float,
    triple_swap_day: str,
) -> float:
    """Sum swap cash for all broker-server rollovers crossed in ``(start, end]``."""
    return sum(
        rollover_swap_cash_from_rates(
            lot=lot,
            direction=direction,
            rollover_timestamp=rollover,
            swap_long_per_lot_usd=swap_long_per_lot_usd,
            swap_short_per_lot_usd=swap_short_per_lot_usd,
            triple_swap_day=triple_swap_day,
        )
        for rollover in broker_server_rollovers_crossed(start, end)
    )


def apply_crossed_rollover_swaps(
    *,
    cash: float,
    position: dict,
    current_time: pd.Timestamp,
    broker: BrokerProfile,
) -> float:
    """Book each newly crossed broker-server rollover exactly once."""
    last_checked = position.get("last_swap_check_time", position["entry_time"])
    direction = str(position.get("direction", "long"))
    swap_total = crossed_rollover_swap_cash(
        start=last_checked,
        end=current_time,
        lot=position["lot"],
        direction=direction,
        swap_long_per_lot_usd=(
            broker.swap_long_points * broker.point * broker.contract_size
        ),
        swap_short_per_lot_usd=(
            broker.swap_short_points * broker.point * broker.contract_size
        ),
        triple_swap_day=broker.triple_swap_day,
    )
    if swap_total:
        position["swap"] += swap_total
        cash += swap_total
    position["last_swap_check_time"] = pd.Timestamp(current_time)
    return cash


def fixed_baseline_smoke_configs(
    timeframe: str, broker: BrokerProfile | None = None
) -> list[dict]:
    """Tiny fixed configuration set for one timeframe; not an optimization grid."""
    normalized_timeframe = normalize_baseline_timeframe(timeframe)
    spread_multipliers = broker.spread_stress_multipliers if broker else (1.0,)
    return [
        {
            "name": (
                f"{normalized_timeframe.lower()}_ema12_26_atr_rr1_"
                f"spread_{spread_multiplier:g}x"
            ),
            "timeframe": normalized_timeframe,
            "atr_multiplier": 1.0,
            "rr": 1.0,
            "lot": 0.10,
            "max_trades": 3,
            "spread_multiplier": spread_multiplier,
        }
        for spread_multiplier in spread_multipliers
    ]


def fixed_m15_smoke_configs(broker: BrokerProfile | None = None) -> list[dict]:
    """Compatibility wrapper for the original M15-only smoke config helper."""
    return fixed_baseline_smoke_configs("M15", broker)


def run_baseline_smoke(
    df: pd.DataFrame, broker: BrokerProfile, config: dict, *, timeframe: str
) -> dict:
    """Run one deterministic directional smoke path from verified Bid OHLC.

    The function purposely uses one position at a time, fixed lot, broker-server
    midnight rollover swap accounting, no historical news filter, and no
    parameter search.
    """
    normalized_timeframe = normalize_baseline_timeframe(timeframe)
    config_timeframe = config.get("timeframe")
    if config_timeframe is not None:
        config_timeframe = normalize_baseline_timeframe(config_timeframe)
        if config_timeframe != normalized_timeframe:
            raise ValueError(
                "Timeframe mismatch between requested run "
                f"{normalized_timeframe!r} and config {config_timeframe!r}"
            )

    data = add_baseline_indicators(df)
    capital = broker.initial_capital_usd
    equity_curve: list[float] = []
    trades: list[dict] = []
    position = None
    spread_multiplier = float(config.get("spread_multiplier", 1.0))
    spread_price = broker.spread_price_for_multiplier(spread_multiplier)
    direction = str(config.get("direction", "long")).lower()
    if direction not in {"long", "short"}:
        raise ValueError("direction must be 'long' or 'short'")

    last_row = None
    for i in range(27, len(data)):
        row = data.iloc[i]
        last_row = row
        prev = data.iloc[i - 1]
        if position is None:
            signal_bar = prev
            signal_prev = data.iloc[i - 2]
            crossed_up = (
                signal_prev["ema_fast"] <= signal_prev["ema_slow"]
                and signal_bar["ema_fast"] > signal_bar["ema_slow"]
            )
            crossed_down = (
                signal_prev["ema_fast"] >= signal_prev["ema_slow"]
                and signal_bar["ema_fast"] < signal_bar["ema_slow"]
            )
            signal = crossed_up if direction == "long" else crossed_down
            if signal and not pd.isna(signal_bar["atr_14"]):
                lot = broker.quantize_lot(config["lot"])
                if lot != 0.0:
                    risk_distance = signal_bar["atr_14"] * config["atr_multiplier"]
                    common_position = {
                        "signal_time": signal_bar.name,
                        "entry_time": row.name,
                        "entry_bid_open": row["open"],
                        "spread_price": spread_price,
                        "spread_multiplier": spread_multiplier,
                        "direction": direction,
                        "lot": lot,
                        "swap": 0.0,
                        "last_swap_check_time": row.name,
                    }
                    if direction == "long":
                        entry_ask = entry_ask_from_bid_close(
                            row["open"], spread_price
                        )
                        position = {
                            **common_position,
                            "entry_ask": entry_ask,
                            "stop_bid": entry_ask - risk_distance,
                            "target_bid": entry_ask + risk_distance * config["rr"],
                        }
                    else:
                        entry_bid = entry_bid_for_short(row["open"])
                        position = {
                            **common_position,
                            "entry_bid": entry_bid,
                            "stop_ask": entry_bid + risk_distance,
                            "target_ask": entry_bid - risk_distance * config["rr"],
                        }

        if position is not None:
            capital = apply_crossed_rollover_swaps(
                cash=capital,
                position=position,
                current_time=row.name,
                broker=broker,
            )
            if direction == "long":
                exit_bid, exit_reason = resolve_long_exit_bid(
                    bar_open_bid=row["open"],
                    bar_high_bid=row["high"],
                    bar_low_bid=row["low"],
                    stop_bid=position["stop_bid"],
                    target_bid=position["target_bid"],
                )
            else:
                exit_bid, exit_reason = resolve_short_exit_bid(
                    bar_open_bid=row["open"],
                    bar_high_bid=row["high"],
                    bar_low_bid=row["low"],
                    stop_ask=position["stop_ask"],
                    target_ask=position["target_ask"],
                    spread_price=spread_price,
                )
            if exit_reason:
                exit_ask = exit_ask_for_short(exit_bid, spread_price)
                price_pnl = (
                    pnl_usd(position["entry_ask"], exit_bid, position["lot"], broker)
                    if direction == "long"
                    else short_pnl_usd(
                        position["entry_bid"], exit_ask, position["lot"], broker
                    )
                )
                trade_pnl = price_pnl + position["swap"]
                capital += price_pnl
                trade = {
                    **position,
                    "timeframe": normalized_timeframe,
                    "exit_time": row.name,
                    "exit_bid": exit_bid,
                    "reason": exit_reason,
                    "price_pnl": price_pnl,
                    "swap": position["swap"],
                    "pnl": trade_pnl,
                }
                if direction == "short":
                    trade["exit_ask"] = exit_ask
                trades.append(trade)
                position = None

        if direction == "long":
            equity = mark_to_market_long_equity(
                capital, position, row["close"], broker
            )
        else:
            equity = mark_to_market_short_equity(
                capital, position, row["close"], broker
            )
        equity_curve.append(equity)
        if len(trades) >= config["max_trades"]:
            break

    if position is not None and last_row is not None:
        exit_bid = exit_bid_for_long(last_row["close"])
        exit_ask = exit_ask_for_short(exit_bid, spread_price)
        price_pnl = (
            pnl_usd(position["entry_ask"], exit_bid, position["lot"], broker)
            if direction == "long"
            else short_pnl_usd(
                position["entry_bid"], exit_ask, position["lot"], broker
            )
        )
        trade_pnl = price_pnl + position["swap"]
        capital += price_pnl
        trade = {
            **position,
            "timeframe": normalized_timeframe,
            "exit_time": last_row.name,
            "exit_bid": exit_bid,
            "reason": "FORCED_FINAL_CLOSE",
            "price_pnl": price_pnl,
            "swap": position["swap"],
            "pnl": trade_pnl,
        }
        if direction == "short":
            trade["exit_ask"] = exit_ask
        trades.append(trade)
        equity_curve[-1] = capital

    return {
        "trades": trades,
        "final_capital": capital,
        "trade_count": len(trades),
        "equity_curve": equity_curve,
    }


def run_m15_baseline_smoke(
    df: pd.DataFrame, broker: BrokerProfile, config: dict
) -> dict:
    """Compatibility wrapper for the original M15-only smoke runner."""
    return run_baseline_smoke(df, broker, config, timeframe="M15")
