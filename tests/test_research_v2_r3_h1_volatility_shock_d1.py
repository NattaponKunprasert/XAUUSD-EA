import ast
import hashlib
import inspect
import json
from pathlib import Path

import pytest
from types import MappingProxyType
import numpy as np
import pandas as pd

import xauusd_ea.research_v2_volatility_shock_d1 as module


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / module.CONTRACT_PATH


def _canonical(payload):
    value = dict(payload); value.pop("contract_sha256", None)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def _bars(count=16):
    # Each prior bar has TR 1; final bar opens/closes inside a non-shock range.
    return [[100.0 + i, 101.0 + i, 100.0 + i, 100.5 + i] for i in range(count)]


def test_contract_and_authority_loader_are_immutable_and_no_market_data_read(monkeypatch):
    payload = json.loads(CONTRACT.read_bytes())
    assert hashlib.sha256(_canonical(payload)).hexdigest() == module.EXPECTED_CONTRACT_SHA256
    reads, original = [], Path.read_bytes
    def traced(path, *args, **kwargs):
        reads.append(Path(path).name); return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_bytes", traced)
    loaded = module.load_research_v2_r3_h1_volatility_shock_d1(ROOT)
    assert loaded["family"]["timeframe"] == "H1"
    assert "XAUUSD_H1.csv" not in reads
    with pytest.raises(TypeError): loaded["family"]["timeframe"] = "M15"


def test_broker_raw_identity_is_the_git_lf_bytes_not_a_local_autocrlf_variant():
    broker = ROOT / "config/xm_micro_gold.json"
    expected = "4a7a6ab6116dd0368e2028493e3f1e646d10e60c78d926fea8f48a9e3e46c45b"
    raw = broker.read_bytes()
    git_lf = raw.replace(b"\r\n", b"\n")
    assert hashlib.sha256(git_lf).hexdigest() == expected
    assert b"\r" not in git_lf
    assert json.loads(raw) == json.loads(git_lf)


def test_git_lf_broker_identity_inventory_is_scoped_to_the_r3_d1_d2_authorities():
    legacy_raw_sha = "baddca3104d70dd470545f3d211e8ca6610588531f11c53ed25e3c06f7e33457"
    git_lf_sha = "4a7a6ab6116dd0368e2028493e3f1e646d10e60c78d926fea8f48a9e3e46c45b"
    contract_sha = "2ee52511b28ebd956e35188e11e97d8351d02047d070873485e0219df8bd1164"
    authority_literals = {
        "config/research_v2_r3_h1_volatility_shock_d1_contract.json": (git_lf_sha,),
        # D1 source authenticates the contract, rather than duplicating the
        # broker digest.  Its authority literal is therefore the contract ID.
        "xauusd_ea/research_v2_volatility_shock_d1.py": (contract_sha,),
        "xauusd_ea/research_v2_volatility_shock_d2.py": (git_lf_sha, contract_sha),
        "config/research_v2_r3_h1_volatility_shock_d2_audit_evidence.json": (git_lf_sha,),
        "tests/fixtures/research_v2_r3_h1_volatility_shock_d2_expected.json": (git_lf_sha,),
    }
    authority_text = {relative: (ROOT / relative).read_text(encoding="utf-8") for relative in authority_literals}
    assert all(legacy_raw_sha not in text for text in authority_text.values())
    for relative, literals in authority_literals.items():
        assert all(literal in authority_text[relative] for literal in literals)
    assert not (ROOT / ".gitattributes").exists()


def test_h1_prefix_raw_identity_is_git_lf_bytes_not_local_autocrlf_variant():
    source = ROOT / "XAUUSD_H1.csv"
    with source.open("rb") as handle:
        local_prefix = b"".join(handle.readline() for _ in range(5001))
    git_lf_prefix = local_prefix.replace(b"\r\n", b"\n")
    expected = "9c3f91e7ec1df8e7b778a797f754c368b8e76a28231480ca616632658e04ecb9"
    assert hashlib.sha256(git_lf_prefix).hexdigest() == expected
    assert b"\r" not in git_lf_prefix
    assert len(git_lf_prefix) == 268364


def test_authenticated_bounded_h1_prefix_is_exact_and_has_no_tail_read(monkeypatch):
    contract = module.load_research_v2_r3_h1_volatility_shock_d1(ROOT)
    calls, original = [], Path.open
    class Reader:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *args): return self.handle.close()
        def readline(self, *args): calls.append("readline"); return self.handle.readline(*args)
    def traced(path, *args, **kwargs): return Reader(original(path, *args, **kwargs))
    monkeypatch.setattr(Path, "open", traced)
    result = module.attest_h1_prefix(ROOT, contract)
    assert result["rows"] == 5000 and result["readline_calls"] == 5001
    assert len(calls) == 5001


@pytest.mark.parametrize("field,value", [("source_path", "XAUUSD_M30.csv"), ("rows", 5001), ("timeframe_minutes", 30), ("legitimate_gap_count", 0)])
def test_caller_prefix_authority_cannot_select_h1_read(monkeypatch, field, value):
    contract = json.loads(CONTRACT.read_bytes()); contract["data_prefix"][field] = value
    opened = []
    def denied(*args, **kwargs): opened.append(args); raise AssertionError("source must not open")
    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(ValueError, match="caller contract drift"):
        module.attest_h1_prefix(ROOT, MappingProxyType(contract))
    assert opened == []


def test_public_attestor_has_only_the_two_declared_arguments_and_private_implementation():
    signature = inspect.signature(module.attest_h1_prefix)
    assert list(signature.parameters) == ["project_root", "contract"]
    assert all(parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values())
    assert module.attest_h1_prefix.__closure__ is not None
    closed = [cell.cell_contents for cell in module.attest_h1_prefix.__closure__]
    assert len(closed) == 1 and inspect.isfunction(closed[0])
    assert "_H1_AUTH" not in module.__dict__
    assert "_implementation" not in module.attest_h1_prefix.__globals__


@pytest.mark.parametrize("keyword", ["_authority", "_authority_binding", "_namespace", "_canonicalizer", "_canonical_binding", "_sha256", "_json_dumps", "_path_type", "_datetime_type", "_timedelta_type", "_freezer", "_thawer", "_mapping_proxy_type"])
def test_authority_or_helper_injection_is_typeerror_before_h1_open(monkeypatch, keyword):
    contract = module.load_research_v2_r3_h1_volatility_shock_d1(ROOT)
    opened = []
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: opened.append(args))
    with pytest.raises(TypeError):
        module.attest_h1_prefix(ROOT, contract, **{keyword: MappingProxyType({})})
    assert opened == []


def test_extra_positional_and_forged_m30_authority_fail_before_h1_open(monkeypatch):
    contract = module.load_research_v2_r3_h1_volatility_shock_d1(ROOT)
    opened = []
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: opened.append(args))
    with pytest.raises(TypeError):
        module.attest_h1_prefix(ROOT, contract, MappingProxyType({"source_path": "XAUUSD_M30.csv"}))
    with pytest.raises(TypeError):
        module.attest_h1_prefix(ROOT, contract, _authority=MappingProxyType({"source_path": "XAUUSD_M30.csv"}))
    assert opened == []


def test_custom_or_forged_contract_mapping_cannot_select_m30_before_h1_open(monkeypatch):
    opened = []
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: opened.append(args))
    for contract in ({"source_path": "XAUUSD_M30.csv"}, MappingProxyType({"source_path": "XAUUSD_M30.csv"})):
        with pytest.raises(ValueError, match="caller contract drift"):
            module.attest_h1_prefix(ROOT, contract)
    assert opened == []


@pytest.mark.parametrize("binding,replacement", [("_canonical", lambda value: b"forged"), ("_thaw", lambda value: {"source_path": "XAUUSD_M30.csv"})])
def test_rebound_public_helpers_cannot_redirect_private_h1_attestation(monkeypatch, binding, replacement):
    contract = module.load_research_v2_r3_h1_volatility_shock_d1(ROOT)
    monkeypatch.setattr(module, binding, replacement)
    result = module.attest_h1_prefix(ROOT, contract)
    assert result["rows"] == 5000 and result["raw_sha256"] == "9c3f91e7ec1df8e7b778a797f754c368b8e76a28231480ca616632658e04ecb9"


def test_h1_redirect_and_contract_drift_fail_closed(tmp_path):
    redirected = tmp_path / "copy.json"; redirected.write_bytes(CONTRACT.read_bytes())
    with pytest.raises(ValueError, match="canonical contract path redirect"):
        module.load_research_v2_r3_h1_volatility_shock_d1(ROOT, contract_path=redirected)
    payload = json.loads(CONTRACT.read_bytes()); payload["signal_contract"]["shock_multiple"] = 1.5
    with pytest.raises(ValueError, match="contract"):
        module._validate_contract(payload)


def test_prior_atr_signal_boundaries_invalidity_and_symmetry():
    bars = _bars()
    # normal final TR is 1, rising body => long
    bars[15] = [115.0, 116.0, 115.0, 115.5]
    assert module.volatility_shock_signal(bars, 15) == 1
    bars[15] = [115.5, 116.0, 115.0, 115.0]
    assert module.volatility_shock_signal(bars, 15) == -1
    # equality with 2 * reference (reference=1) abstains
    bars[15] = [115.0, 117.5, 115.0, 116.0]
    assert module.volatility_shock_signal(bars, 15) == 0
    bars[15] = [115.0, 116.0, 115.0, 115.0]
    assert module.volatility_shock_signal(bars, 15) == 0
    bars[4][1] = float("nan")
    assert module.volatility_shock_signal(bars, 15) == 0
    for malformed in (None, "not-a-bar", [1.0, 2.0], [1.0, None, 0.0, 1.0], [1.0, 0.0, 1.0, 1.0], [object(), 1.0, 0.0, 1.0]):
        broken = _bars(); broken[4] = malformed
        assert module.volatility_shock_signal(broken, 15) == 0
    for field in range(4):
        for scalar in ("115.0", b"115.0", True):
            broken = _bars(); broken[15][field] = scalar
            assert module.volatility_shock_signal(broken, 15) == 0
    numeric = [[np.float64(o), np.float64(h), np.float64(l), pd.Series([c], dtype="float64").iloc[0]] for o, h, l, c in _bars()]
    assert module.volatility_shock_signal(numeric, 15) == 1
    bars = _bars(); bars[15] = [115.0, 116.0, 115.0, 115.5]
    inverted = [[-o, -l, -h, -c] for o, h, l, c in bars]
    assert module.volatility_shock_signal(inverted, 15) == -module.volatility_shock_signal(bars, 15)
    assert module.volatility_shock_signal(bars, 14) == 0


def test_module_has_no_engine_d2_or_d3_imports():
    source = Path(module.__file__).read_text(encoding="utf-8")
    imports = [node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom) and node.module]
    assert not any("baseline" in name or name.endswith("_d2") or name.endswith("_d3") for name in imports)
