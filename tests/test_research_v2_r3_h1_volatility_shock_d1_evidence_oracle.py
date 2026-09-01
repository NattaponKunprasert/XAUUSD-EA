import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "config/research_v2_r3_h1_volatility_shock_d1_audit_evidence.json"


def test_terminal_d1_evidence_binds_exact_contract_and_no_engine_scope():
    value = json.loads(EVIDENCE.read_bytes())
    assert value["audit_status"] == "PASS"
    assert value["decision"] == "D1_GATE_PASSED_D2_NOT_RUN"
    assert value["data_prefix"]["row_indices"] == "[0,5000)"
    assert value["signal"]["first_eligible_closed_bar_index"] == 15
    assert all(value["scope"].values())
    assert value["audit_history"][-1] == {
        "stage": "m206_independent_audit",
        "result": "PASS",
        "terminal": "AUDIT: PASS",
        "findings": [],
        "repair_cycles": 0,
    }
    for key in ("contract", "loader", "test"):
        item = value["bindings"][key]
        assert hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["file_sha256" if key == "contract" else "sha256"]
    fixture = value["bindings"]["fixture"]
    assert hashlib.sha256((ROOT / fixture["path"]).read_bytes()).hexdigest() == fixture["sha256"]
