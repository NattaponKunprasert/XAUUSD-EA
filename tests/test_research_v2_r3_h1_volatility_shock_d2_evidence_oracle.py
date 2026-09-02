import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "config/research_v2_r3_h1_volatility_shock_d2_audit_evidence.json"
FIXTURE = ROOT / "tests/fixtures/research_v2_r3_h1_volatility_shock_d2_expected.json"
ORACLE = ROOT / "tests/fixtures/research_v2_r3_h1_volatility_shock_d2_oracle.json"


def test_m211_pending_evidence_fixture_live_bindings_and_swap_oracle_are_exact():
    evidence = json.loads(EVIDENCE.read_bytes())
    assert evidence == json.loads(FIXTURE.read_bytes())
    assert (evidence["audit_status"], evidence["decision"], evidence["promotion_label"]) == (
        "PENDING_AUDIT", "D2_M211_HERMETIC_COORDINATOR_PENDING_AUDIT_D3_NOT_RUN", "research"
    )
    for name in ("source", "test", "runtime"):
        binding = evidence["bindings"][name]
        assert hashlib.sha256((ROOT / binding["path"]).read_bytes()).hexdigest() == binding["sha256"]
    broker = evidence["bindings"]["broker"]
    broker_bytes = (ROOT / broker["path"]).read_bytes().replace(b"\r\n", b"\n")
    assert b"\r" not in broker_bytes
    assert hashlib.sha256(broker_bytes).hexdigest() == broker["sha256"]
    oracle = json.loads(ORACLE.read_bytes())
    assert oracle == {
        "signal_first_eligible": 15, "execution_offset_bars": 1,
        "spreads": [1.0, 1.5, 2.0], "contract_size": 1.0, "fixed_lot": 0.1,
        "long_swap_points": -93.39, "short_swap_points": 10.74,
        "ordinary_long_swap_usd": -0.09339, "ordinary_short_swap_usd": 0.01074,
        "wednesday_long_swap_usd": -0.28017, "wednesday_short_swap_usd": 0.03222,
        "isolated_worker_boundary": "two fresh python -I -B workers receive exact source snapshots by stdin; mode nonce pid and complete report bytes bind replay",
    }


def test_d2_source_remains_d3_holdout_forward_and_csv_free():
    source = (ROOT / "xauusd_ea/research_v2_volatility_shock_d2.py").read_text(encoding="utf-8").lower()
    for forbidden in ("read_csv(", "xauusd_h1.csv", "holdout", "forward", "_d3"):
        assert forbidden not in source
