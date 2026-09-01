import math
import sys
from types import FunctionType, MappingProxyType, ModuleType
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xauusd_ea.research_v2_volatility_shock_d2 as d2

from xauusd_ea.research_v2_volatility_shock_d2 import _load_authorities, run_synthetic_h1_volatility_shock_d2, validate_exact_d1_volatility_shock_h1_slice

ROOT = Path(__file__).resolve().parents[1]

def bars(n=22):
    index = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({"open":np.full(n,100.),"high":np.full(n,101.),"low":np.full(n,99.),"close":np.full(n,100.),"volume":np.ones(n)},index=index)

def cfg(**changes):
    value={"timeframe":"H1","direction":"both","atr_period":14,"atr_multiplier":1.,"rr":1.,"lot":.1,"spread_multiplier":1.}; value.update(changes); return value

def held_signal_bars(start, direction, n=41):
    """Create a D1-valid, open position which survives to forced close."""
    index = pd.date_range(start, periods=n, freq="h")
    close = 101. if direction == "long" else 99.
    source = pd.DataFrame({"open":100.,"high":105.,"low":95.,"close":100.,"volume":1}, index=index)
    source.iloc[15] = [100., 105., 95., close, 1]
    return source

def sealed_pathlib_module():
    """Reach the actual runner closure bundle as an adversarial caller can."""
    pending, visited = [run_synthetic_h1_volatility_shock_d2], set()
    while pending:
        item = pending.pop()
        if id(item) in visited:
            continue
        visited.add(id(item))
        if isinstance(item, FunctionType):
            pending.extend(cell.cell_contents for cell in (item.__closure__ or ()) if cell.cell_contents is not item)
        elif isinstance(item, MappingProxyType):
            if isinstance(item.get("pathlib"), ModuleType):
                return item["pathlib"]
            pending.extend(item.values())
        elif isinstance(item, dict):
            pending.extend(item.values())
    raise AssertionError("sealed pathlib module was not reachable")

def exact_h1():
    raw = pd.read_csv(ROOT / "XAUUSD_H1.csv", sep="\t", skiprows=1, names=["time","open","high","low","close","volume"]).iloc[:5000]
    raw["time"] = pd.to_datetime(raw["time"], format="%Y.%m.%d %H:%M")
    return raw.set_index("time").rename_axis("time").astype({"open":"float64","high":"float64","low":"float64","close":"float64","volume":"int64"})

def test_authorities_bind_terminal_d1_and_broker():
    contract, broker, _ = _load_authorities(ROOT)
    assert contract["data_prefix"]["rows"] == 5000
    assert (broker.symbol, broker.contract_size, broker.spread_stress_multipliers) == ("GOLDmicro",1.,(1.,1.5,2.))

def test_rejects_noncanonical_root_before_engine():
    with pytest.raises(ValueError):
        run_synthetic_h1_volatility_shock_d2(bars(), cfg(), project_root=ROOT.parent)

@pytest.mark.parametrize("spread",[1.,1.5,2.])
def test_next_bar_bid_ask_and_forced_close(spread):
    source=bars(); source.iloc[15]=[100.,100.8,99.8,100.5,1.]
    source.iloc[16:,:] = [100.,100.1,99.9,100.,1.]
    out=run_synthetic_h1_volatility_shock_d2(source,cfg(spread_multiplier=spread))
    assert out["trade_count"] == 1
    trade=out["trades"][0]
    assert trade["signal_time"] == source.index[15] and trade["entry_time"] == source.index[16]
    assert trade["direction"] == "long" and trade["reason"] == "FORCED_FINAL_CLOSE"
    assert trade["entry"] == pytest.approx(100.+.551142857142857*spread)

def test_invalid_and_equal_bars_abstain():
    source=bars(); source.iloc[15]=[100.,101.,99.,100.,1.]
    assert run_synthetic_h1_volatility_shock_d2(source,cfg())["trade_count"] == 0
    source=bars(); source.iloc[15,0]=math.nan
    with pytest.raises(ValueError): run_synthetic_h1_volatility_shock_d2(source,cfg())

def test_one_position_and_accounting_are_finite():
    source=bars(30)
    for i in (15,18,21): source.iloc[i]=[100.,100.8,99.8,100.5,1.]
    out=run_synthetic_h1_volatility_shock_d2(source,cfg())
    assert out["trade_count"] <= 1 and all(math.isfinite(v) for v in out["equity_curve"])

def test_public_runner_captures_authority_path_and_rejects_helper_kwargs(monkeypatch):
    calls=[]
    monkeypatch.setattr(d2, "_sealed_reader", lambda *a, **k: calls.append(True))
    monkeypatch.setattr(d2, "Path", lambda *a, **k: pytest.fail("rebound Path used"))
    out=run_synthetic_h1_volatility_shock_d2(bars(), cfg())
    assert out["trade_count"] == 0 and calls == []
    with pytest.raises(TypeError): run_synthetic_h1_volatility_shock_d2(bars(), cfg(), _authority_loader=lambda: None)

@pytest.mark.parametrize("name,start,stop", [("fold1_train",0,2000),("fold2_train",1000,3000),("fold3_train",2000,4000),("fold1_test",2000,3000),("fold2_test",3000,4000),("fold3_test",4000,5000)])
def test_exact_six_h1_slices_bind_order_dtype_and_identity(name,start,stop):
    source = exact_h1()
    validate_exact_d1_volatility_shock_h1_slice(source.iloc[start:stop], name)
    with pytest.raises(ValueError): validate_exact_d1_volatility_shock_h1_slice(source.iloc[start:stop].iloc[::-1], name)
    changed=source.iloc[start:stop].copy(); changed.iloc[0,0] += .01
    with pytest.raises(ValueError): validate_exact_d1_volatility_shock_h1_slice(changed, name)

def test_complete_5000_row_deletion_matrix_fails_exact_slice_identity():
    source=exact_h1()
    # Each source row belongs to at least one declared contiguous slice.  This
    # is intentionally the complete 5,000-row deletion matrix, not sampling.
    specs=(("fold1_train",0,2000),("fold2_train",1000,3000),("fold3_train",2000,4000),("fold3_test",4000,5000))
    for row in range(5000):
        name,start,stop=next(item for item in specs if item[1] <= row < item[2])
        damaged=source.iloc[start:stop].drop(source.index[row])
        with pytest.raises(ValueError): validate_exact_d1_volatility_shock_h1_slice(damaged,name)

def test_parent_ambient_pathlib_proxy_cannot_change_isolated_authoritative_result(monkeypatch):
    proxy = ModuleType("pathlib")
    opened=[]
    class ProxyPath:
        def __init__(self, *args): opened.append(args)
    proxy.Path = ProxyPath
    monkeypatch.setitem(sys.modules, "pathlib", proxy)
    baseline = run_synthetic_h1_volatility_shock_d2(bars(), cfg())
    assert run_synthetic_h1_volatility_shock_d2(bars(), cfg()) == baseline
    assert opened == []

def test_parent_pathlib_attribute_mutation_cannot_change_isolated_result(monkeypatch):
    import pathlib
    opened=[]
    class CachedPath:
        def __init__(self, *args): opened.append(args)
    monkeypatch.setattr(pathlib, "Path", CachedPath)
    baseline = run_synthetic_h1_volatility_shock_d2(bars(), cfg())
    assert run_synthetic_h1_volatility_shock_d2(bars(), cfg()) == baseline
    assert opened == []

def test_parent_public_runner_has_no_reachable_private_engine_bundle():
    # The former in-process closure bundle was intentionally removed.  A
    # caller can inspect this wrapper, but it cannot obtain the child engine.
    with pytest.raises(AssertionError):
        sealed_pathlib_module()
    assert not hasattr(d2, "_run_synthetic_in_worker")


def test_d2_runtime_authority_is_minimal_and_does_not_bind_user_baseline():
    authority = dict(d2._AUTHORITY)
    assert "xauusd_ea/baseline.py" not in authority
    assert authority["xauusd_ea/d2_runtime_primitives.py"]
    source = (ROOT / "xauusd_ea/research_v2_volatility_shock_d2.py").read_text(encoding="utf-8")
    assert "xauusd_ea/baseline.py" not in source


def test_public_kwargs_and_old_local_worker_flag_cannot_bypass_isolation(monkeypatch):
    with pytest.raises(TypeError):
        run_synthetic_h1_volatility_shock_d2(bars(), cfg(), _snapshots={})
    monkeypatch.setattr(d2, "_D2_ISOLATED_WORKER", True, raising=False)
    assert run_synthetic_h1_volatility_shock_d2(bars(), cfg())["trade_count"] == 0


def test_controller_ignores_forged_module_launcher_and_globals(monkeypatch):
    forged = {"schema": 1, "mode": "research", "nonce": "x", "pid": 7,
              "report": {"final_capital": 999999}, "report_sha256": "x",
              "manifest": {}, "cwd": str(ROOT.parent)}
    monkeypatch.setattr(d2, "_launch_isolated_worker", lambda payload: (forged, b"forged"), raising=False)
    monkeypatch.setattr(d2, "_ROOT_TEXT", str(ROOT.parent), raising=False)
    monkeypatch.setattr(d2, "_D2_PATH", "redirect.py", raising=False)
    assert run_synthetic_h1_volatility_shock_d2(bars(), cfg())["final_capital"] == pytest.approx(1000.)
    with pytest.raises(ValueError):
        run_synthetic_h1_volatility_shock_d2(bars(), cfg(), project_root=ROOT.parent)


def test_hermetic_bootstrap_declares_isolated_cwd_trace_and_manifest_checks():
    source = d2._WORKER_BOOTSTRAP
    for required in ("sys.flags.isolated", "dont_write_bytecode", "sys.gettrace", "sys.getprofile", "manifest=", "cwd"):
        assert required in source
    assert "_run_synthetic_in_worker" not in source
    assert "open(origin" not in source

def test_peak_relative_drawdown_is_measured_at_loss_before_later_profit():
    source=bars(28)
    source.iloc[15]=[100.,100.5,99.5,100.4,1.]
    source.iloc[16]=[100.,100.1,95.,96.,1.]       # long SL
    source.iloc[17]=[96.,96.5,95.5,96.4,1.]
    source.iloc[18]=[96.,105.,95.5,104.,1.]       # later long TP
    out=run_synthetic_h1_volatility_shock_d2(source,cfg())
    assert [item["reason"] for item in out["trades"]] == ["SL","TP"]
    assert out["final_capital"] > 1000.
    assert out["max_drawdown"] == pytest.approx(0.1928571428571786)
    assert out["max_drawdown_fraction"] == pytest.approx(0.0001928571428571786)

@pytest.mark.parametrize("spread,expected", [(1.,-0.055114285714286386),(2.,-0.11022857142857134)])
def test_short_entry_is_bid_and_forced_exit_is_ask_with_declared_spread(spread, expected):
    source=bars(22); source.iloc[15]=[100.,100.8,99.2,99.5,1.]
    source.iloc[16:]=[100.,100.1,99.9,100.,1.]
    trade=run_synthetic_h1_volatility_shock_d2(source,cfg(spread_multiplier=spread))["trades"][0]
    assert (trade["direction"],trade["entry"],trade["exit_bid"],trade["reason"]) == ("short",100.,100.,"FORCED_FINAL_CLOSE")
    assert trade["price_pnl"] == pytest.approx(expected)

@pytest.mark.parametrize("direction", ["long","short"])
def test_conservative_same_bar_ambiguity_is_stop_first(direction):
    source=bars(22)
    source.iloc[15]=[100.,100.8,99.2,100.5 if direction == "long" else 99.5,1.]
    source.iloc[16]=[100.,103.,97.,100.,1.]
    trade=run_synthetic_h1_volatility_shock_d2(source,cfg())["trades"][0]
    assert trade["direction"] == direction and trade["reason"] == "SL"

@pytest.mark.parametrize(("direction", "raw_points", "expected_swap"), [
    ("long", -93.39, -0.09339), ("short", 10.74, 0.01074),
])
def test_long_and_short_overnight_swap_prices_pnl_equity_and_forced_close(direction, raw_points, expected_swap):
    # Sunday 08:00 -> entry Monday 00:00 -> one ordinary Tuesday rollover.
    contract, broker, _ = _load_authorities(ROOT)
    source = held_signal_bars("2024-01-07 08:00", direction)
    out = run_synthetic_h1_volatility_shock_d2(source, cfg())
    trade = out["trades"][0]
    assert (broker.swap_long_points if direction == "long" else broker.swap_short_points) == raw_points
    assert trade["reason"] == "FORCED_FINAL_CLOSE"
    assert trade["entry"] == pytest.approx(100.55114285714286 if direction == "long" else 100.)
    assert trade["exit_bid"] == pytest.approx(100.)
    assert trade["price_pnl"] == pytest.approx(-0.055114285714286386)
    assert trade["swap"] == pytest.approx(expected_swap)
    assert trade["pnl"] == pytest.approx(trade["price_pnl"] + expected_swap)
    assert out["final_capital"] == pytest.approx(1000. + trade["pnl"])
    assert out["equity_curve"][-1] == pytest.approx(out["final_capital"])

@pytest.mark.parametrize(("direction", "raw_points", "expected_swap"), [
    ("long", -93.39, -0.28017), ("short", 10.74, 0.03222),
])
def test_long_and_short_wednesday_triple_swap_prices_pnl_equity_and_forced_close(direction, raw_points, expected_swap):
    # Monday 08:00 -> entry Tuesday 00:00 -> one Wednesday triple rollover.
    _, broker, _ = _load_authorities(ROOT)
    source = held_signal_bars("2024-01-08 08:00", direction)
    out = run_synthetic_h1_volatility_shock_d2(source, cfg())
    trade = out["trades"][0]
    assert (broker.swap_long_points if direction == "long" else broker.swap_short_points) == raw_points
    assert trade["reason"] == "FORCED_FINAL_CLOSE"
    assert trade["entry"] == pytest.approx(100.55114285714286 if direction == "long" else 100.)
    assert trade["exit_bid"] == pytest.approx(100.)
    assert trade["price_pnl"] == pytest.approx(-0.055114285714286386)
    assert trade["swap"] == pytest.approx(expected_swap)
    assert trade["pnl"] == pytest.approx(trade["price_pnl"] + expected_swap)
    assert out["final_capital"] == pytest.approx(1000. + trade["pnl"])
    assert out["equity_curve"][-1] == pytest.approx(out["final_capital"])
