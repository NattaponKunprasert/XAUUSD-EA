"""Fail-closed Research v2 Round-3 H1 D1 declaration and signal contract.

This module deliberately has no engine, candidate, D2, or D3 imports.  Its only
market-data operation is the explicit 5,001-line H1 attestation below.
"""

from __future__ import annotations

import hashlib
import json
import math
from numbers import Real
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Sequence


CONTRACT_PATH = "config/research_v2_r3_h1_volatility_shock_d1_contract.json"
EXPECTED_CONTRACT_SHA256 = "869a167f72ab1f1a977deecc2c6eb26fcde0cbb65c1040917df4521130688625"
_CONTRACT_FILE_SHA256 = "3f2cc2a71265f28556b4511a60488ca2a5f0a6066ca11e89c3ddfd072ed5d0fc"
_D0_EVIDENCE = ("config/research_v2_d0_audit_evidence.json", "2923817be7c360abbd8abdaa9605b650afb16bfdde2f6e30bc38c5ea19422428")
_AGENDA = ("config/research_v2_d0_agenda.json", "0de16daa6ac2da11bf667399b4f3c3bb40a04863a7cac4cb5a84b0be9ddc840f", "bd7c5042acbf196f6bd8d362bce2622f41e17004d72816aa0ce4e514cb659ff2")
_ROUND2 = ("config/research_v2_r2_m30_regime_direction_d3_audit_evidence.json", "75f219700f3f6d040268af3c3c33c3abc5c947091a370d8953b339c978fb2bff")


def _canonical(value: dict[str, Any]) -> bytes:
    copied = dict(value); copied.pop("contract_sha256", None)
    return json.dumps(copied, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def _thaw(value: Any, recurse: Any = None) -> Any:
    """Materialize only ordinary frozen JSON-shaped contract values."""
    if recurse is None:
        recurse = _thaw
    if type(value) is MappingProxyType:
        return {key: recurse(item, recurse) for key, item in value.items()}
    if isinstance(value, tuple):
        return [recurse(item, recurse) for item in value]
    if isinstance(value, list):
        return [recurse(item, recurse) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _read_exact(root: Path, relative: str, expected: str, label: str) -> bytes:
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"v2 volatility shock D1 {label} canonical path drift")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"v2 volatility shock D1 {label} unavailable") from exc
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"v2 volatility shock D1 {label} identity drift")
    return data


def _read_git_lf_exact(root: Path, relative: str, expected: str, label: str) -> bytes:
    """Bind the broker profile to its Git-LF content, not checkout EOLs."""
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"v2 volatility shock D1 {label} canonical path drift")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"v2 volatility shock D1 {label} unavailable") from exc
    canonical = data.replace(b"\r\n", b"\n")
    if b"\r" in canonical or hashlib.sha256(canonical).hexdigest() != expected:
        raise ValueError(f"v2 volatility shock D1 {label} identity drift")
    return canonical


def _validate_contract(contract: dict[str, Any]) -> None:
    required = {"schema_version", "contract_id", "contract_sha256", "audit_status", "decision", "d1_runtime_proof", "labels", "d0_binding", "round2_terminal_binding", "broker_binding", "family", "signal_contract", "data_prefix", "windows", "prohibitions"}
    signal = contract.get("signal_contract", {})
    data = contract.get("data_prefix", {})
    windows = contract.get("windows", {})
    valid = (
        set(contract) == required
        and contract["schema_version"] == 1
        and contract["contract_id"] == "research_v2_r3_h1_volatility_shock_abstention_d1"
        and contract["audit_status"] == "PENDING_BUILDER"
        and contract["decision"] == "D1_DECLARED_AUDIT_PENDING_D2_NOT_RUN"
        and contract["d1_runtime_proof"] is False
        and contract["family"] == {"agenda_order": 3, "agenda_round_id": "v2_r3_h1_volatility_shock_abstention", "mechanism": "VOLATILITY_SHOCK_ABSTENTION", "timeframe": "H1", "assignment_rationale": "The prior-14-TR reference adds a second rolling state and is assigned third to the next supported duration by implementation simplicity only."}
        and signal.get("tr_period") == 14 and type(signal.get("tr_period")) is int
        and signal.get("shock_multiple") == 2.0 and type(signal.get("shock_multiple")) is float
        and signal.get("first_eligible_closed_bar_index") == 15 and type(signal.get("first_eligible_closed_bar_index")) is int
        and signal.get("shock_rule") == "abstain when TR[t] >= 2.0 * reference_atr14[t]"
        and signal.get("long") == "TR[t] < 2.0 * reference_atr14[t] and close[t] > open[t]"
        and signal.get("short") == "TR[t] < 2.0 * reference_atr14[t] and close[t] < open[t]"
        and data.get("source_path") == "XAUUSD_H1.csv" and data.get("rows") == 5000 and data.get("readline_calls") == 5001
        and data.get("row_index_start") == 0 and data.get("row_index_stop_exclusive") == 5000
        and data.get("timeframe_minutes") == 60 and data.get("tail_bound") is False
        and windows.get("N") == 5000 and windows.get("q") == 1000 and windows.get("remainder_count") == 0
        and [(item.get("train_rows"), item.get("test_rows")) for item in windows.get("folds", [])] == [("[0,2000)", "[2000,3000)"), ("[1000,3000)", "[3000,4000)"), ("[2000,4000)", "[4000,5000)")]
        and all(value is True for value in contract["prohibitions"].values())
    )
    if not valid:
        raise ValueError("v2 volatility shock D1 contract semantic or schema drift")


def load_research_v2_r3_h1_volatility_shock_d1(project_root: str | Path, *, contract_path: str | Path | None = None) -> MappingProxyType:
    """Authenticate D0, Round2 sequencing and declaration authorities only."""
    root = Path(project_root).resolve()
    target = root / CONTRACT_PATH
    if contract_path is not None and Path(contract_path).resolve() != target.resolve():
        raise ValueError("v2 volatility shock D1 canonical contract path redirect")
    contract_bytes = _read_exact(root, CONTRACT_PATH, _CONTRACT_FILE_SHA256, "contract")
    try:
        contract = json.loads(contract_bytes)
        _validate_contract(contract)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("v2 volatility shock D1 contract identity or schema drift") from exc
    if contract["contract_sha256"] != EXPECTED_CONTRACT_SHA256 or hashlib.sha256(_canonical(contract)).hexdigest() != EXPECTED_CONTRACT_SHA256:
        raise ValueError("v2 volatility shock D1 contract identity drift")
    d0 = json.loads(_read_exact(root, *_D0_EVIDENCE, "D0 evidence"))
    if (d0.get("audit_status"), d0.get("decision"), d0.get("promotion_label"), d0.get("audit_history", [{}])[-1].get("terminal")) != ("PASS", "D0_GATE_PASSED_D1_NOT_RUN", "research", "AUDIT: PASS"):
        raise ValueError("v2 volatility shock D1 D0 evidence drift")
    agenda = json.loads(_read_exact(root, _AGENDA[0], _AGENDA[1], "agenda"))
    if hashlib.sha256(_canonical(agenda)).hexdigest() != _AGENDA[2] or agenda.get("rounds", [{}, {}, {}])[2].get("round_id") != "v2_r3_h1_volatility_shock_abstention":
        raise ValueError("v2 volatility shock D1 agenda drift")
    round2 = json.loads(_read_exact(root, *_ROUND2, "Round2 terminal evidence"))
    if (round2.get("audit_status"), round2.get("promotion_label"), round2.get("scope", {}).get("v2_round2_complete")) != ("PASS", "research", True):
        raise ValueError("v2 volatility shock D1 Round2 sequencing drift")
    broker = contract["broker_binding"]
    profile = json.loads(_read_git_lf_exact(root, broker["config_path"], broker["sha256"], "broker"))
    if (profile.get("symbol"), profile.get("contract_size"), profile.get("ohlc_price_source"), profile.get("commission_per_lot_round_turn_usd"), profile.get("fee_per_lot_round_turn_usd")) != ("GOLDmicro", 1.0, "bid", 0.0, 0.0):
        raise ValueError("v2 volatility shock D1 broker drift")
    return _freeze(contract)


def _bar_values(bar: Any) -> tuple[float, float, float, float] | None:
    """Coerce precisely four ordinary finite scalar values, otherwise None."""
    try:
        if isinstance(bar, (str, bytes)) or len(bar) != 4:
            return None
        raw = tuple(bar[item] for item in range(4))
        if any(isinstance(value, bool) or not isinstance(value, Real) for value in raw):
            return None
        values = tuple(float(value) for value in raw)
        if not all(math.isfinite(value) for value in values):
            return None
        opening, high, low, close = values
        return values if high >= low and low <= opening <= high and low <= close <= high else None
    except Exception:  # malformed user-supplied bar implementations are no-signal
        return None


def _valid_bar(bar: Any) -> bool:
    return _bar_values(bar) is not None


def volatility_shock_signal(bars: Sequence[Sequence[float]], index: int) -> int:
    """Return +1/0/-1 for one fully closed H1 bar, without execution side effects."""
    try:
        count = len(bars)
    except Exception:
        return 0
    if type(index) is not int or index < 15 or index >= count:
        return 0
    try:
        required = range(index - 14, index + 1)
        values = {item: _bar_values(bars[item]) for item in range(index - 15, index + 1)}
        if any(values[item] is None for item in required):
            return 0
        tr = []
        for item in required:
            current, previous = values[item], values[item - 1]
            if current is None or previous is None:
                return 0
            _, high, low, _ = current
            tr.append(max(high - low, abs(high - previous[3]), abs(low - previous[3])))
    except Exception:
        return 0
    reference = sum(tr[:14]) / 14.0
    current = tr[14]
    opening, _, _, close = values[index]  # proven non-None above
    if not math.isfinite(reference) or reference <= 0.0 or current >= 2.0 * reference:
        return 0
    return 1 if close > opening else -1 if close < opening else 0


def _make_h1_prefix_attestor() -> Any:
    """Bind the H1 authority and every attestation primitive once at import.

    The returned public wrapper intentionally closes over only this private
    implementation.  Normal callers cannot supply an authority, namespace, or
    helper; contract is an identity assertion, never a source selector.
    """
    authority = MappingProxyType({
        "source_path": "XAUUSD_H1.csv", "rows": 5000, "readline_calls": 5001,
        "raw_header_bytes": 33, "prefix_snapshot_bytes": 273365,
        "prefix_snapshot_sha256": "9f05df5271b6ad74e2c15064569d2cf9e853bf8b69c9db521fe44af7da6cc942",
        "canonical_ohlcv_sha256": "0bb8b073705249dbc5be46d2250b6b08a6a8f6a5dc21336eeee0b2d828f6ea69",
        "timestamp_sequence_sha256": "0532730fa58c2087cc37b428ee5b8e8799a51d3137e5c0739c059adf49ce6f48",
        "first_timestamp": "2023-01-03T01:00:00", "last_timestamp": "2023-11-03T20:00:00",
        "complete_coverage_end": "2023-11-03T21:00:00", "legitimate_gap_count": 217,
        "gap_schedule_sha256": "8c98a6907a080530d057dcc498fef7d991bc55d32dd58fb39c8f826489c9c058",
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
    })
    sha256, json_dumps = hashlib.sha256, json.dumps
    path_type, datetime_type, timedelta_type = Path, datetime, timedelta
    proxy_type, value_error, os_error = MappingProxyType, ValueError, OSError

    def thawer(value: Any) -> Any:
        if type(value) is proxy_type:
            return {key: thawer(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return [thawer(item) for item in value]
        if isinstance(value, list):
            return [thawer(item) for item in value]
        return value

    def canonicalizer(value: dict[str, Any]) -> bytes:
        copied = dict(value)
        copied.pop("contract_sha256", None)
        return json_dumps(copied, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()

    def freezer(value: Any) -> Any:
        if isinstance(value, dict):
            return proxy_type({key: freezer(item) for key, item in value.items()})
        if isinstance(value, list):
            return tuple(freezer(item) for item in value)
        return value

    def _implementation(project_root: str | Path, contract: MappingProxyType) -> MappingProxyType:
        try:
            if type(contract) is not proxy_type or sha256(canonicalizer(thawer(contract))).hexdigest() != authority["contract_sha256"]:
                raise value_error("v2 volatility shock D1 caller contract drift")
        except (ArithmeticError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise value_error("v2 volatility shock D1 caller contract drift") from exc
        root = path_type(project_root).resolve()
        path = root / authority["source_path"]
        if path.is_symlink() or not path.is_file() or path.resolve() != path.absolute():
            raise value_error("v2 volatility shock D1 H1 canonical path drift")
        lines: list[bytes] = []
        try:
            with path.open("rb") as handle:
                for _ in range(authority["readline_calls"]):
                    line = handle.readline()
                    if not line:
                        raise value_error("v2 volatility shock D1 H1 prefix truncated")
                    lines.append(line)
        except os_error as exc:
            raise value_error("v2 volatility shock D1 H1 unavailable") from exc
        snapshot = b"".join(lines)
        if len(lines[0]) != authority["raw_header_bytes"] or len(snapshot) != authority["prefix_snapshot_bytes"] or sha256(snapshot).hexdigest() != authority["prefix_snapshot_sha256"]:
            raise value_error("v2 volatility shock D1 H1 prefix identity drift")
        if lines[0].decode("ascii").strip() != "Time,Open,High,Low,Close,Volume":
            raise value_error("v2 volatility shock D1 H1 header drift")
        rows = [line.decode("ascii").strip().split("\t") for line in lines[1:]]
        if len(rows) != authority["rows"] or any(len(row) != 6 for row in rows):
            raise value_error("v2 volatility shock D1 H1 mixed CSV schema drift")
        try:
            times = [datetime_type.strptime(row[0], "%Y.%m.%d %H:%M") for row in rows]
            values = [[float(row[1]), float(row[2]), float(row[3]), float(row[4]), int(row[5])] for row in rows]
        except (TypeError, ValueError) as exc:
            raise value_error("v2 volatility shock D1 H1 dtype drift") from exc
        canonical = {"columns": ("open", "high", "low", "close", "volume"), "index": [item.isoformat() for item in times], "values": values}
        gaps = [{"after_index": item, "from": earlier.isoformat(), "to": later.isoformat(), "delta_minutes": int((later-earlier).total_seconds()/60)} for item, (earlier, later) in enumerate(zip(times, times[1:])) if later - earlier != timedelta_type(hours=1)]
        if (sha256(json_dumps(canonical, allow_nan=False, separators=(",", ":")).encode()).hexdigest(), sha256(json_dumps([item.isoformat() for item in times], separators=(",", ":")).encode()).hexdigest(), sha256(json_dumps(gaps, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), len(gaps)) != (authority["canonical_ohlcv_sha256"], authority["timestamp_sequence_sha256"], authority["gap_schedule_sha256"], authority["legitimate_gap_count"]):
            raise value_error("v2 volatility shock D1 H1 canonical chronology drift")
        if (times[0].isoformat(), times[-1].isoformat(), (times[-1] + timedelta_type(hours=1)).isoformat()) != (authority["first_timestamp"], authority["last_timestamp"], authority["complete_coverage_end"]):
            raise value_error("v2 volatility shock D1 H1 endpoint drift")
        return freezer({"rows": len(rows), "first_timestamp": times[0].isoformat(), "last_timestamp": times[-1].isoformat(), "readline_calls": len(lines), "raw_sha256": sha256(snapshot).hexdigest()})

    def attest_h1_prefix(project_root: str | Path, contract: MappingProxyType) -> MappingProxyType:
        return _implementation(project_root, contract)

    return attest_h1_prefix


attest_h1_prefix = _make_h1_prefix_attestor()
del _make_h1_prefix_attestor
