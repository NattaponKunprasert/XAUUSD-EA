"""Round-3 H1 D2 synthetic execution boundary (never a research runner).

The exported runner closes over a sealed descriptor reader.  It intentionally
does not use mutable module globals while authenticating or dispatching.
"""
from __future__ import annotations

import hashlib
import builtins
import io
import json
import math
import os
import pathlib
import re
import stat
import sys
import dataclasses
import datetime
import numbers
import types
import typing
import base64
import subprocess
import tempfile
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Mapping

import numpy as np
import pandas as pd

_ROOT_TEXT = str(Path(__file__).resolve().parents[1])
_D2_SOURCE_TEXT = str(Path(__file__).resolve())
_AUTHORITY = (
    ("config/research_v2_r3_h1_volatility_shock_d1_audit_evidence.json", "06ad8d39020a26f73f48b415908855773f4ed572e56fd9daa092a99149ecce1a"),
    ("config/research_v2_r3_h1_volatility_shock_d1_contract.json", "3f2cc2a71265f28556b4511a60488ca2a5f0a6066ca11e89c3ddfd072ed5d0fc"),
    ("config/xm_micro_gold.json", "4a7a6ab6116dd0368e2028493e3f1e646d10e60c78d926fea8f48a9e3e46c45b"),
    ("xauusd_ea/d2_runtime_primitives.py", "a7aa0474337fc108f71fe063ac3365df542eb9922077a40efca44d2c95296dab"),
    ("xauusd_ea/research_v2_volatility_shock_d1.py", "a3147fa4995b92fa3bff0c53cfbf76741bdc469e2cdbb4d2a65bc89b36e0aa0c"),
    ("tests/test_research_v2_r3_h1_volatility_shock_d1.py", "28301553298a7e7bbf8bd83fe82d8b8f4318c4f2b9c0ede3be8278c5a6974121"),
)
_D1_CANONICAL_SHA = "869a167f72ab1f1a977deecc2c6eb26fcde0cbb65c1040917df4521130688625"


def _make_sealed_d2():
    """Bind all authority primitives once, including descriptor-level I/O."""
    path_type, root_text, authority_specs, d1_canonical = Path, _ROOT_TEXT, _AUTHORITY, _D1_CANONICAL_SHA
    # Only the isolated child supplies this mapping.  It is intentionally read
    # once while building the child-private closure: authenticated source code
    # must never be reopened from the repository by the child.
    supplied_sources = globals().get("_D2_ISOLATED_SOURCE_SNAPSHOTS")
    root_type = type(path_type(root_text))
    allowed = MappingProxyType(dict(authority_specs))
    os_open, os_read, os_close, os_stat, fd_stat = os.open, os.read, os.close, os.stat, os.fstat
    flags, nofollow = os.O_RDONLY | getattr(os, "O_BINARY", 0), getattr(os, "O_NOFOLLOW", 0)
    is_regular, sha256, loads, dumps = stat.S_ISREG, hashlib.sha256, json.loads, json.dumps
    module_type, modules, compiler, executor = ModuleType, sys.modules, compile, exec
    runtime_modules = MappingProxyType({name: modules[name] for name in (
        "hashlib", "io", "json", "math", "re", "dataclasses", "pathlib", "typing",
        "numbers", "datetime", "types", "numpy", "pandas",
    )})
    sys_module = sys
    builtin_dict, real_import = dict(builtins.__dict__), builtins.__import__
    # All aliases directly consumed by authenticated D2 runtime/D1 source.  The
    # private compiler receives frozen-by-isolation module copies; this list is
    # separately checked so an in-place attribute replacement also fails.
    import_attributes = MappingProxyType({
        "hashlib": ("sha256",), "json": ("loads", "dumps"), "math": ("isfinite", "fsum"),
        "dataclasses": ("dataclass",), "pathlib": ("Path",), "typing": ("Any", "Mapping", "Iterable", "Sequence"),
        "numbers": ("Real",), "datetime": ("datetime", "timedelta"), "types": ("MappingProxyType",),
    })
    get_attr, tuple_fn, set_fn = getattr, tuple, set
    captured_attributes = MappingProxyType({(name, attr): get_attr(runtime_modules[name], attr) for name, attrs in import_attributes.items() for attr in attrs})
    # MappingProxyType protects only the mapping, not the mutable module copies
    # held as its values.  The private importer is therefore guarded by a full
    # module-dictionary identity inventory.  It deliberately includes every
    # attribute, rather than just the direct aliases above: an in-place edit to
    # ``sealed_modules['pathlib'].Path`` (or an added/deleted attribute) must
    # fail before the private compiler can import it.
    sealed_copies = {name: (lambda original, name=name: (lambda copy: (copy.__dict__.update(original.__dict__), copy)[1])(module_type(name)))(item) for name, item in runtime_modules.items()}
    sealed_modules = MappingProxyType(sealed_copies)
    sealed_attribute_snapshots = MappingProxyType({
        name: MappingProxyType(dict(copy.__dict__)) for name, copy in sealed_copies.items()
    })

    def validate_import_authority() -> None:
        if sys_module.modules is not modules or any(modules.get(name) is not item for name, item in runtime_modules.items()):
            raise error("Volatility Shock D2 ambient import authority drift")
        if any(get_attr(runtime_modules[name], attr, None) is not expected for (name, attr), expected in captured_attributes.items()):
            raise error("Volatility Shock D2 ambient import attribute drift")
        for name, expected in sealed_attribute_snapshots.items():
            candidate = sealed_modules.get(name)
            if candidate is not sealed_copies[name] or set_fn(candidate.__dict__) != set_fn(expected):
                raise error("Volatility Shock D2 sealed import inventory drift")
            if any(candidate.__dict__[attr] is not value for attr, value in expected.items()):
                raise error("Volatility Shock D2 sealed import attribute drift")

    def sealed_import(name, globals_=None, locals_=None, fromlist=(), level=0):
        if level == 0 and name in sealed_modules:
            return sealed_modules[name]
        return real_import(name, globals_, locals_, fromlist, level)
    # CPython requires a concrete dict for a frame's __builtins__ lookup.
    # This dict is private to the factory and never returned to callers.
    sealed_builtins = builtin_dict | {"__import__": sealed_import}
    dataframe, datetime_index, np_mod, pd_mod = pd.DataFrame, pd.DatetimeIndex, np, pd
    finite, error, type_fn, tuple_fn, len_fn = math.isfinite, ValueError, type, tuple, len

    def canonical_root(root: str | Path) -> Any:
        text = root if type_fn(root) is str else str(root) if type_fn(root) is root_type else None
        if text != root_text:
            raise error("Volatility Shock D2 authority root drift")
        item = path_type(root_text)
        if str(item.resolve()) != root_text or not item.is_dir() or item.is_symlink():
            raise error("Volatility Shock D2 canonical root drift")
        junction = getattr(item, "is_junction", None)
        if junction is not None and junction():
            raise error("Volatility Shock D2 canonical root reparse drift")
        return item

    def read(relative: str) -> bytes:
        expected = allowed.get(relative)
        if type_fn(relative) is not str or expected is None or "\\" in relative or any(piece in ("", ".", "..") for piece in relative.split("/")):
            raise error("Volatility Shock D2 authority path drift")
        if supplied_sources is not None and relative in supplied_sources:
            raw = supplied_sources[relative]
            canonical = raw.replace(b"\r\n", b"\n") if relative == "config/xm_micro_gold.json" else raw
            if type_fn(raw) is not bytes or (relative == "config/xm_micro_gold.json" and b"\r" in canonical) or sha256(canonical).hexdigest() != expected:
                raise error("Volatility Shock D2 passed-source identity drift")
            return canonical
        root = canonical_root(root_text); target = root.joinpath(*relative.split("/")); text = str(target)
        if str(target.resolve()) != text or target.is_symlink() or not target.is_file():
            raise error("Volatility Shock D2 authority redirect")
        try:
            before = os_stat(text, follow_symlinks=False); fd = os_open(text, flags | nofollow)
            try:
                bound = fd_stat(fd)
                if not is_regular(bound.st_mode) or (before.st_dev, before.st_ino, before.st_size) != (bound.st_dev, bound.st_ino, bound.st_size):
                    raise error("Volatility Shock D2 authority descriptor drift")
                chunks = []
                while True:
                    value = os_read(fd, 65536)
                    if not value: break
                    chunks.append(value)
            finally:
                os_close(fd)
            after = os_stat(text, follow_symlinks=False)
        except OSError as exc:
            raise error("Volatility Shock D2 authority unavailable") from exc
        if (after.st_dev, after.st_ino, after.st_size) != (before.st_dev, before.st_ino, before.st_size) or str(target.resolve()) != text:
            raise error("Volatility Shock D2 authority TOCTOU drift")
        raw = b"".join(chunks)
        canonical = raw.replace(b"\r\n", b"\n") if relative == "config/xm_micro_gold.json" else raw
        if len_fn(raw) != before.st_size or (relative == "config/xm_micro_gold.json" and b"\r" in canonical) or sha256(canonical).hexdigest() != expected:
            raise error("Volatility Shock D2 authority identity drift")
        return canonical

    def contract_hash(contract: Mapping[str, Any]) -> str:
        payload = dict(contract); payload.pop("contract_sha256", None)
        return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

    def private_dependencies(runtime_raw: bytes, d1_raw: bytes) -> Mapping[str, Any]:
        # The interpreter import cache is itself authority.  Do not repair or
        # silently replace an ambient entry: reject before compiling either
        # authenticated source if an attacker supplied a proxy module.
        validate_import_authority()
        before = dict(modules); base_name, d1_name = "_r3_h1_d2_runtime", "_r3_h1_d2_d1"
        try:
            base = module_type(base_name); base.__file__ = str(path_type(root_text) / "xauusd_ea/d2_runtime_primitives.py"); modules[base_name] = base
            base.__dict__["__builtins__"] = sealed_builtins
            executor(compiler(runtime_raw, base.__file__, "exec"), base.__dict__)
            d1 = module_type(d1_name); d1.__file__ = str(path_type(root_text) / "xauusd_ea/research_v2_volatility_shock_d1.py"); modules[d1_name] = d1
            d1.__dict__["__builtins__"] = sealed_builtins
            executor(compiler(d1_raw, d1.__file__, "exec"), d1.__dict__)
            validate_import_authority()
            needed = ("load_broker_profile_snapshot", "add_baseline_indicators", "entry_ask_from_bid_close", "entry_bid_for_short", "exit_ask_for_short", "pnl_usd", "short_pnl_usd", "mark_to_market_long_equity", "mark_to_market_short_equity", "resolve_long_exit_bid", "resolve_short_exit_bid", "apply_crossed_rollover_swaps", "_validated_directional_risk_levels")
            if any(not callable(base.__dict__.get(name)) for name in needed) or any(not callable(d1.__dict__.get(name)) for name in ("volatility_shock_signal", "attest_h1_prefix", "load_research_v2_r3_h1_volatility_shock_d1")):
                raise error("Volatility Shock D2 private dependency drift")
            return MappingProxyType({name: base.__dict__[name] for name in needed} | {"signal": d1.volatility_shock_signal, "attest": d1.attest_h1_prefix, "load_d1": d1.load_research_v2_r3_h1_volatility_shock_d1})
        finally:
            for name in list(modules):
                if name not in before: del modules[name]
            modules.update(before)

    def authorities(root: str | Path = root_text) -> tuple[Mapping[str, Any], Any, Mapping[str, Any]]:
        canonical_root(root)
        evidence_raw, contract_raw, broker_raw, runtime_raw, d1_raw, _ = (read(name) for name, _ in authority_specs)
        try: evidence, contract = loads(evidence_raw), loads(contract_raw)
        except (TypeError, ValueError) as exc: raise error("Volatility Shock D2 authority JSON drift") from exc
        binding = evidence.get("bindings", {}).get("contract", {}) if type_fn(evidence) is dict else {}
        if (evidence.get("audit_status"), evidence.get("decision"), evidence.get("promotion_label"), evidence.get("audit_history", [{}])[-1].get("terminal")) != ("PASS", "D1_GATE_PASSED_D2_NOT_RUN", "research", "AUDIT: PASS") or (binding.get("path"), binding.get("file_sha256"), binding.get("canonical_sha256")) != (authority_specs[1][0], authority_specs[1][1], d1_canonical):
            raise error("Volatility Shock D2 terminal D1 evidence drift")
        signal, prefix = contract.get("signal_contract", {}), contract.get("data_prefix", {})
        if contract_hash(contract) != d1_canonical or contract.get("contract_id") != "research_v2_r3_h1_volatility_shock_abstention_d1" or (signal.get("tr_period"), signal.get("shock_multiple"), signal.get("first_eligible_closed_bar_index"), prefix.get("rows"), prefix.get("timeframe_minutes")) != (14, 2.0, 15, 5000, 60):
            raise error("Volatility Shock D2 D1 contract drift")
        private = private_dependencies(runtime_raw, d1_raw); broker = private["load_broker_profile_snapshot"](broker_raw)
        if (broker.symbol, broker.contract_size, broker.ohlc_price_source, broker.quantize_lot(.1), broker.min_lot, broker.spread_stress_multipliers) != ("GOLDmicro", 1.0, "bid", .1, .1, (1.0, 1.5, 2.0)):
            raise error("Volatility Shock D2 broker literal drift")
        validate_import_authority()
        # The terminal D1 contract above was parsed from authenticated passed
        # bytes.  Passing that immutable mapping avoids calling D1's public
        # repository loader in the isolated child.
        # The D1 public attestor is deliberately not an authority in a child:
        # it uses ``Path.open``.  The D2 worker instead reads the one allowed
        # H1 prefix through the captured descriptor primitives and verifies the
        # D1 contract literals before any synthetic dispatch.
        h1_name = "XAUUSD_" + "H1.csv"
        target = canonical_root(root_text) / h1_name
        if target.is_symlink() or not target.is_file() or str(target.resolve()) != str(target):
            raise error("Volatility Shock D2 H1 descriptor path drift")
        try:
            before = os_stat(str(target), follow_symlinks=False)
            fd = os_open(str(target), flags | nofollow)
            try:
                bound = fd_stat(fd)
                if not is_regular(bound.st_mode) or (before.st_dev, before.st_ino) != (bound.st_dev, bound.st_ino):
                    raise error("Volatility Shock D2 H1 descriptor identity drift")
                lines, pending = [], b""
                while len(lines) < 5001:
                    part = os_read(fd, 65536)
                    if not part:
                        raise error("Volatility Shock D2 H1 prefix truncated")
                    pending += part
                    pieces = pending.splitlines(keepends=True)
                    pending = b"" if pending.endswith(b"\n") else pieces.pop()
                    lines.extend(pieces)
                if len(lines) != 5001:
                    # The last chunk may contain a following row; retain only
                    # the declared prefix and reject a malformed boundary.
                    lines = lines[:5001]
            finally:
                os_close(fd)
            after = os_stat(str(target), follow_symlinks=False)
        except OSError as exc:
            raise error("Volatility Shock D2 H1 unavailable") from exc
        if (after.st_dev, after.st_ino, after.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise error("Volatility Shock D2 H1 descriptor TOCTOU drift")
        snapshot = b"".join(lines)
        if (len(snapshot), sha256(snapshot).hexdigest(), lines[0].decode("ascii").strip()) != (prefix["prefix_snapshot_bytes"], prefix["prefix_snapshot_sha256"], "Time,Open,High,Low,Close,Volume"):
            raise error("Volatility Shock D2 H1 prefix identity drift")
        proof = {"rows": 5000, "raw_sha256": sha256(snapshot).hexdigest()}
        validate_import_authority()
        if proof["rows"] != 5000 or proof["raw_sha256"] != prefix["prefix_snapshot_sha256"]: raise error("Volatility Shock D2 H1 prefix drift")
        return MappingProxyType(contract), broker, private

    def validate_frame(df: pd.DataFrame) -> None:
        if type_fn(df) is not dataframe or tuple_fn(df.columns) != ("open", "high", "low", "close", "volume") or type_fn(df.index) is not datetime_index or df.index.tz is not None or not df.index.is_monotonic_increasing or df.index.has_duplicates or len_fn(df) < 17:
            raise error("Volatility Shock D2 synthetic Bid OHLCV schema drift")
        values = df.iloc[:, :4].to_numpy(dtype=float)
        if not np_mod.isfinite(values).all() or (df.high < df.low).any() or (df.high < df[["open", "close"]].max(axis=1)).any() or (df.low > df[["open", "close"]].min(axis=1)).any(): raise error("Volatility Shock D2 synthetic Bid OHLCV value drift")

    def validate_config(config: Mapping[str, Any]) -> tuple[float, float, float]:
        if type_fn(config) is not dict or set(config) != {"timeframe", "direction", "atr_period", "atr_multiplier", "rr", "lot", "spread_multiplier"} or (config["timeframe"], config["direction"], config["atr_period"], config["lot"]) != ("H1", "both", 14, .1): raise error("Volatility Shock D2 fixed config drift")
        a, r, s = config["atr_multiplier"], config["rr"], config["spread_multiplier"]
        if any(type_fn(x) is not float for x in (a, r, s)) or a not in (1., 1.5, 2.) or r not in (1., 1.5, 2.) or s not in (1., 1.5, 2.): raise error("Volatility Shock D2 package drift")
        return a, r, s

    slices = (
        ("fold1_train", 0, 2000, "2023-01-03T01:00:00", "2023-05-05T03:00:00", "879880bd6fb08e89d18902b1129e7869b431a01ffa66b4ff855173d519fe591a"),
        ("fold2_train", 1000, 3000, "2023-03-03T16:00:00", "2023-07-05T20:00:00", "7254f9a6bcfb09a22b8cab5c3135ad4e84a7fd82da047230d015f4e9ec171fed"),
        ("fold3_train", 2000, 4000, "2023-05-05T04:00:00", "2023-09-05T10:00:00", "be2c85e0ce0b7de9530a6c0b9d948c07fa613d7a606ae870d05088c6248bf7c5"),
        ("fold1_test", 2000, 3000, "2023-05-05T04:00:00", "2023-07-05T20:00:00", "074e63419439661a203e381a32f27974ef92e03fa354abbd34d2664da0b96890"),
        ("fold2_test", 3000, 4000, "2023-07-05T21:00:00", "2023-09-05T10:00:00", "1c64cb5f77f41ac3c459e8bbd72f746247b551322e1f2f2fd9a4c42cb5122e1d"),
        ("fold3_test", 4000, 5000, "2023-09-05T11:00:00", "2023-11-03T20:00:00", "84329c1a178169d8e3c1218e9cf50dafa0be05d46bfc38878961b187dd93bb3e"),
    )

    def validate_exact_slice(df: pd.DataFrame, slice_id: str) -> None:
        """Verify one declared D1 H1 slice; never opens source data."""
        validate_frame(df)
        match = next((item for item in slices if item[0] == slice_id), None)
        if match is None: raise error("Volatility Shock D2 undeclared exact slice")
        _, start, stop, first, last, expected = match
        if len_fn(df) != stop-start or df.index[0].isoformat() != first or df.index[-1].isoformat() != last or tuple_fn(df.dtypes.astype(str)) != ("float64", "float64", "float64", "float64", "int64"):
            raise error("Volatility Shock D2 exact slice range or dtype drift")
        identity = {"columns":[{"name":c,"dtype":str(df[c].dtype)} for c in df.columns],"index_name":df.index.name,"index_dtype":str(df.index.dtype),"index":[item.isoformat() for item in df.index],"values":[[float(a),float(b),float(c),float(d),int(e)] for a,b,c,d,e in df.itertuples(index=False,name=None)]}
        if sha256(dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest() != expected: raise error("Volatility Shock D2 exact slice identity drift")

    def run(df: pd.DataFrame, config: dict[str, Any], *, project_root: str | Path = root_text) -> dict[str, Any]:
        _, broker, private = authorities(project_root); validate_frame(df); atr_mult, rr, mult = validate_config(config)
        # No user-controlled frame/config method is called after this final
        # sealed-import check and before synthetic engine dispatch.
        validate_import_authority()
        lot, spread, cash = broker.quantize_lot(.1), broker.spread_price_for_multiplier(mult), broker.initial_capital_usd
        if lot != .1: raise error("Volatility Shock D2 upward sizing prohibited")
        trades, equity, position = [], [], None
        for index in range(16, len_fn(df)):
            row = df.iloc[index]
            if position is None:
                signal_index, signal = index - 1, private["signal"](df.iloc[:, :4].to_numpy(), index - 1); atr = float(private["add_baseline_indicators"](df.iloc[:index])["atr_14"].iloc[-1])
                if signal and finite(atr) and atr > 0:
                    direction = "long" if signal > 0 else "short"; entry = private["entry_ask_from_bid_close"](row.open, spread) if signal > 0 else private["entry_bid_for_short"](row.open); stop, target = private["_validated_directional_risk_levels"](direction=direction, entry_price=entry, signal_atr=atr, atr_multiplier=atr_mult, rr=rr); position = {"direction":direction,"entry":entry,"signal_time":df.index[signal_index],"entry_time":row.name,"lot":lot,"swap":0.,"last_swap_check_time":row.name,"stop":stop,"target":target}
            if position:
                cash = private["apply_crossed_rollover_swaps"](cash=cash, position=position, current_time=row.name, broker=broker)
                if position["direction"] == "long": exit_bid, reason = private["resolve_long_exit_bid"](bar_open_bid=row.open,bar_high_bid=row.high,bar_low_bid=row.low,stop_bid=position["stop"],target_bid=position["target"]); pnl = private["pnl_usd"](position["entry"], exit_bid, lot, broker) if reason else 0.
                else: exit_bid, reason = private["resolve_short_exit_bid"](bar_open_bid=row.open,bar_high_bid=row.high,bar_low_bid=row.low,stop_ask=position["stop"],target_ask=position["target"],spread_price=spread); pnl = private["short_pnl_usd"](position["entry"],private["exit_ask_for_short"](exit_bid,spread),lot,broker) if reason else 0.
                if reason: cash += pnl; trades.append({**position,"exit_time":row.name,"exit_bid":exit_bid,"reason":reason,"price_pnl":pnl,"pnl":pnl+position["swap"],"timeframe":"H1"}); position=None
            marked = cash if position is None else (private["mark_to_market_long_equity"](cash,{"entry_ask":position["entry"],"lot":lot},row.close,broker) if position["direction"] == "long" else private["mark_to_market_short_equity"](cash,{"entry_bid":position["entry"],"lot":lot},private["exit_ask_for_short"](row.close,spread),broker)); equity.append(float(marked))
        if position:
            last=df.iloc[-1]; close_time=pd_mod.Timestamp(last.name)+pd_mod.DateOffset(hours=1); cash=private["apply_crossed_rollover_swaps"](cash=cash,position=position,current_time=close_time,broker=broker); exit_bid=float(last.close); pnl=private["pnl_usd"](position["entry"],exit_bid,lot,broker) if position["direction"]=="long" else private["short_pnl_usd"](position["entry"],private["exit_ask_for_short"](exit_bid,spread),lot,broker); cash += pnl; trades.append({**position,"exit_time":close_time,"exit_bid":exit_bid,"reason":"FORCED_FINAL_CLOSE","price_pnl":pnl,"pnl":pnl+position["swap"],"timeframe":"H1"}); equity[-1]=cash
        peak, dd, dd_fraction = broker.initial_capital_usd, 0., 0.
        for value in equity:
            peak=max(peak,value); draw=peak-value
            dd=max(dd,draw); dd_fraction=max(dd_fraction,draw/peak if peak else 0.)
        return {"trades":trades,"trade_count":len_fn(trades),"final_capital":cash,"equity_curve":equity,"max_drawdown":dd,"max_drawdown_fraction":dd_fraction}
    return read, authorities, validate_exact_slice, run


# Parent exports only descriptor/readiness helpers.  It deliberately discards
# the factory after extracting those non-engine validators, so an importer
# cannot materialize a local engine.  A child receives the same authenticated
# source with its stdin snapshots already present and retains the factory only
# long enough to invoke the fourth return value locally.
if globals().get("_D2_ISOLATED_SOURCE_SNAPSHOTS") is None:
    _sealed_reader, _load_authorities, validate_exact_d1_volatility_shock_h1_slice, _discarded = _make_sealed_d2()
    del _discarded, _make_sealed_d2


# The parent deliberately has no callable path to the synthetic engine.  It
# authenticates immutable bytes, launches two fresh isolated interpreters, and
# compares their complete reports.  The child compiles this exact D2 snapshot
# with ``_D2_ISOLATED_WORKER`` set, so its closure reads D1/runtime/config only
# from stdin snapshots and performs the one permitted H1 descriptor read.
_D2_PATH = "xauusd_ea/research_v2_volatility_shock_d2.py"
_WORKER_TIMEOUT_SECONDS = 90
_MAX_IPC_BYTES = 8_000_000


def _wire_value(value):
    if isinstance(value, dict):
        return {str(key): _wire_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire_value(item) for item in value]
    if hasattr(value, "isoformat"):
        return {"__d2_time__": value.isoformat()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError("Volatility Shock D2 report serialization drift")


_WORKER_BOOTSTRAP = r'''
import base64,json,os,sys
payload=json.loads(sys.stdin.buffer.read().decode("utf-8"))
if set(payload)!={"schema","mode","nonce","root","sources","frame","config"} or payload["schema"]!=1 or payload["mode"] not in ("research","verification") or not isinstance(payload["nonce"],str) or not isinstance(payload["root"],str): raise SystemExit(2)
sources={k:base64.b64decode(v.encode("ascii"),validate=True) for k,v in payload["sources"].items()}
source=sources.pop("xauusd_ea/research_v2_volatility_shock_d2.py",None)
if not isinstance(source,bytes): raise SystemExit(3)
if sys.flags.isolated != 1 or sys.flags.dont_write_bytecode != 1 or sys.gettrace() is not None or sys.getprofile() is not None: raise SystemExit(4)
if os.getcwd()==payload["root"] or any(item in ("", payload["root"]) for item in sys.path): raise SystemExit(5)
namespace={"__name__":"_r3_h1_d2_isolated","__file__":os.path.join(payload["root"], "xauusd_ea", "research_v2_volatility_shock_d2.py"),"_D2_ISOLATED_SOURCE_SNAPSHOTS":sources,"_sealed_reader":lambda relative: sources[relative]}
exec(compile(source, namespace["__file__"], "exec"),namespace)
import pandas as pd
frame=payload["frame"]
df=pd.DataFrame(frame["rows"],columns=("open","high","low","close","volume"),index=pd.to_datetime(frame["index"]))
df=df.astype({"open":"float64","high":"float64","low":"float64","close":"float64","volume":"int64"})
out=namespace["_make_sealed_d2"]()[3](df,payload["config"])
def wire(v):
 if isinstance(v,dict): return {str(k):wire(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)): return [wire(x) for x in v]
 if hasattr(v,"isoformat"): return {"__d2_time__":v.isoformat()}
 if isinstance(v,(str,int,float,bool)) or v is None:return v
 raise TypeError(type(v).__name__)
inner=json.dumps(wire(out),allow_nan=False,sort_keys=True,separators=(",",":"))
manifest={"interpreter":sys.implementation.name,"isolated":sys.flags.isolated,"dont_write_bytecode":sys.flags.dont_write_bytecode,"sources":{name:__import__("hashlib").sha256(value).hexdigest() for name,value in sorted({**sources,"xauusd_ea/research_v2_volatility_shock_d2.py":source}.items())}}
envelope={"schema":1,"mode":payload["mode"],"nonce":payload["nonce"],"pid":os.getpid(),"report":json.loads(inner),"report_sha256":__import__("hashlib").sha256(inner.encode()).hexdigest(),"manifest":manifest,"cwd":os.getcwd()}
sys.stdout.write(json.dumps(envelope,allow_nan=False,sort_keys=True,separators=(",",":")))
'''


def _read_own_d2_source(*, _source_text=_D2_SOURCE_TEXT, _path_type=pathlib.Path, _stat=os.stat, _open=os.open, _read=os.read, _close=os.close) -> bytes:
    path = _path_type(_source_text)
    if path.name != "research_v2_volatility_shock_d2.py" or path.is_symlink():
        raise ValueError("Volatility Shock D2 own source authority drift")
    before = _stat(str(path), follow_symlinks=False)
    fd = _open(str(path), os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        chunks = []
        while True:
            chunk = _read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
    finally:
        _close(fd)
    after = _stat(str(path), follow_symlinks=False)
    if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size) or not raw:
        raise ValueError("Volatility Shock D2 own source identity drift")
    return raw


def _read_d2_evidence_source_digest(*, _root_text=_ROOT_TEXT, _d2_path="xauusd_ea/research_v2_volatility_shock_d2.py", _path_type=pathlib.Path, _stat=os.stat, _open=os.open, _read=os.read, _close=os.close, _loads=json.loads) -> str:
    """Read the independent preliminary D2 evidence through one stable fd."""
    relative = "config/research_v2_r3_h1_volatility_shock_d2_audit_evidence.json"
    root = _path_type(_root_text)
    path = root.joinpath(*relative.split("/"))
    if path.is_symlink() or not path.is_file() or str(path.resolve()) != str(path):
        raise ValueError("Volatility Shock D2 evidence descriptor path drift")
    before = _stat(str(path), follow_symlinks=False)
    fd = _open(str(path), os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        chunks = []
        while True:
            value = _read(fd, 65536)
            if not value:
                break
            chunks.append(value)
    finally:
        _close(fd)
    after = _stat(str(path), follow_symlinks=False)
    if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("Volatility Shock D2 evidence TOCTOU drift")
    try:
        evidence = _loads(b"".join(chunks))
        binding = evidence["bindings"]["source"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Volatility Shock D2 evidence schema drift") from exc
    decision = "D2_M211_HERMETIC_COORDINATOR_PENDING_AUDIT_" + "D3_NOT_RUN"
    if (evidence.get("audit_status"), evidence.get("decision"), evidence.get("promotion_label"), binding.get("path")) != ("PENDING_AUDIT", decision, "research", _d2_path) or type(binding.get("sha256")) is not str:
        raise ValueError("Volatility Shock D2 evidence authority drift")
    return binding["sha256"]


def _parent_source_snapshots(project_root: str | Path, *, _root_text=_ROOT_TEXT, _d2_path="xauusd_ea/research_v2_volatility_shock_d2.py", _authority=_AUTHORITY, _path_type=Path, _reader=_sealed_reader, _own_reader=_read_own_d2_source, _evidence_digest=_read_d2_evidence_source_digest, _sha=hashlib.sha256) -> dict[str, bytes]:
    """Read every authority once with the sealed descriptor reader."""
    root = _path_type(project_root).resolve()
    if str(root) != _root_text:
        raise ValueError("Volatility Shock D2 authority root drift")
    paths = tuple(relative for relative, _digest in _authority)
    values = {relative: _reader(relative) for relative in paths}
    own = _own_reader()
    if _sha(own).hexdigest() != _evidence_digest():
        raise ValueError("Volatility Shock D2 current source evidence drift")
    values[_d2_path] = own
    if any(not isinstance(value, bytes) for value in values.values()):
        raise ValueError("Volatility Shock D2 parent source snapshot drift")
    return values


def _frame_wire(df: pd.DataFrame) -> dict[str, object]:
    if type(df) is not pd.DataFrame:
        raise ValueError("Volatility Shock D2 synthetic frame type drift")
    return {
        "index": [value.isoformat() for value in df.index],
        "rows": [[float(a), float(b), float(c), float(d), int(e)] for a, b, c, d, e in df.itertuples(index=False, name=None)],
    }


def _unwire_value(value):
    if isinstance(value, dict):
        if set(value) == {"__d2_time__"}:
            return pd.Timestamp(value["__d2_time__"])
        return {key: _unwire_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_unwire_value(item) for item in value]
    return value


def _launch_isolated_worker(payload: dict[str, object], *, _dumps=json.dumps, _loads=json.loads, _length=len,
                            _max=_MAX_IPC_BYTES, _bootstrap=_WORKER_BOOTSTRAP, _subprocess=subprocess,
                            _temporary=tempfile.TemporaryDirectory, _executable=sys.executable,
                            _path=os.environ.get("PATH", ""), _systemroot=os.environ.get("SYSTEMROOT", "")) -> tuple[dict[str, object], bytes]:
    raw = _dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if _length(raw) > _max:
        raise ValueError("Volatility Shock D2 IPC request too large")
    # Temporary cwd makes ambient relative imports/files unavailable.  ``-I``
    # ignores user site and PYTHONPATH; the bootstrap receives all authority
    # source bytes through stdin.
    with _temporary(prefix="r3_h1_d2_") as cwd:
        completed = _subprocess.run(
            [_executable, "-I", "-B", "-c", _bootstrap], input=raw,
            stdout=_subprocess.PIPE, stderr=_subprocess.PIPE, cwd=cwd,
            env={"PATH": _path, "SYSTEMROOT": _systemroot},
            timeout=_WORKER_TIMEOUT_SECONDS, check=False,
        )
    if completed.returncode or completed.stderr or _length(completed.stdout) > _max:
        raise ValueError("Volatility Shock D2 isolated worker failure: " + completed.stderr.decode("utf-8", "replace")[:2000])
    try:
        envelope = _loads(completed.stdout)
    except (TypeError, ValueError) as exc:
        raise ValueError("Volatility Shock D2 isolated worker IPC drift") from exc
    if type(envelope) is not dict:
        raise ValueError("Volatility Shock D2 isolated worker envelope drift")
    return envelope, completed.stdout


def _make_parent_controller():
    """Capture the complete parent authority graph exactly once.

    This is deliberately a controller, not an engine: its only executable
    child boundary is the captured process launcher.  Deleting this factory
    after construction makes module-global monkeypatches irrelevant.
    """
    snapshots_fn, frame_fn, launch = _parent_source_snapshots, _frame_wire, _launch_isolated_worker
    root_text, d2_path = _ROOT_TEXT, "xauusd_ea/research_v2_volatility_shock_d2.py"
    b64encode, nonce_bytes, dumps, loads, sha, unwire, interpreter = base64.b64encode, os.urandom, json.dumps, json.loads, hashlib.sha256, _unwire_value, sys.implementation.name

    def runner(df: pd.DataFrame, config: dict[str, Any], *, project_root: str | Path = root_text) -> dict[str, Any]:
        """Execute only in two fresh authenticated isolated workers."""
        snapshots = snapshots_fn(project_root)
        if not snapshots.get(d2_path):
            raise ValueError("Volatility Shock D2 source snapshot drift")
        frame = frame_fn(df)
        expected_manifest = {"interpreter": interpreter, "isolated": 1, "dont_write_bytecode": 1,
                             "sources": {key: sha(value).hexdigest() for key, value in sorted(snapshots.items())}}
        canonical_reports, manifests, seen_pids = [], [], set()
        for mode, nonce in (("research", nonce_bytes(24).hex()), ("verification", nonce_bytes(24).hex())):
            sources = {key: b64encode(value).decode("ascii") for key, value in snapshots.items()}
            payload = {"schema": 1, "mode": mode, "nonce": nonce, "root": root_text, "sources": sources, "frame": frame, "config": config}
            envelope, _raw = launch(payload)
            if set(envelope) != {"schema", "mode", "nonce", "pid", "report", "report_sha256", "manifest", "cwd"} or envelope["schema"] != 1 or envelope["mode"] != mode or envelope["nonce"] != nonce or type(envelope["pid"]) is not int or envelope["pid"] in seen_pids or envelope["cwd"] == root_text or envelope["manifest"] != expected_manifest:
                raise ValueError("Volatility Shock D2 isolated worker attestation drift")
            report = dumps(envelope["report"], allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if sha(report).hexdigest() != envelope["report_sha256"]:
                raise ValueError("Volatility Shock D2 isolated worker report hash drift")
            seen_pids.add(envelope["pid"]); canonical_reports.append(report); manifests.append(envelope["manifest"])
        if canonical_reports[0] != canonical_reports[1] or manifests[0] != manifests[1]:
            raise ValueError("Volatility Shock D2 isolated worker replay drift")
        return unwire(loads(canonical_reports[0]))
    return runner


run_synthetic_h1_volatility_shock_d2 = _make_parent_controller()
del _make_parent_controller, _parent_source_snapshots, _frame_wire, _launch_isolated_worker
