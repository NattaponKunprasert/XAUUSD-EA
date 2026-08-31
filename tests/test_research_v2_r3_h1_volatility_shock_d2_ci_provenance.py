import hashlib
import json
import re
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/xauusd-d2-ci-attestation.yml"
SCRIPT = ROOT / "tools/build_d2_ci_provenance.py"
PINS = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    "actions/attest": "1e69f48acb82d1966a394da916b4c1698aa569d6",
}


def _build(output: Path) -> None:
    subprocess.run([
        sys.executable, "-B", str(SCRIPT), "--root", str(ROOT), "--output", str(output),
        "--commit-sha", "a" * 40, "--repository", "example/xauusd", "--run-id", "7",
        "--run-attempt", "1", "--server-url", "https://github.example",
    ], check=True)


def test_ci_workflow_is_narrow_least_privilege_and_requires_remote_attestation():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source and "push:" in source and "pull_request:" in source
    for forbidden in ("schedule:", "contents: write", "pull-requests:", "packages: write", "deployments:"):
        assert forbidden not in source
    for required in (
        "contents: read", "id-token: write", "attestations: write", "--no-cache-dir",
        "--only-binary=:all:", "--require-hashes", "config/d2_ci_requirements.lock",
        "--cache-clear", "subject-path: d2-ci-provenance.json",
        "github.event.pull_request.head.repo.full_name == github.repository",
        "xauusd_ea/research_v2_volatility_shock_d2.py", "config/xm_micro_gold.json",
    ):
        assert required in source
    assert "python-version: \"3.11\"" in source and "Verified from official action refs" in source
    uses = dict(re.findall(r"uses:\s+([^@\s]+)@([^\s#]+)", source))
    assert uses == PINS
    assert all(re.fullmatch(r"[0-9a-f]{40}", value) for value in uses.values())


def test_ci_provenance_builder_is_canonical_bounded_and_contains_only_identities(tmp_path):
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    _build(first); _build(second)
    assert first.read_bytes() == second.read_bytes()
    report = json.loads(first.read_bytes())
    assert report["schema_version"] == 1
    assert report["attestation_status"] == "PENDING_CI_ATTESTATION"
    assert report["promotion_label"] == "research"
    assert report["test"]["status"] == "passed"
    assert all(report["scope_prohibitions"].values())
    assert "not an attestation" in report["external_authority_limit"]
    assert report["ci"]["workflow_path"] == ".github/workflows/xauusd-d2-ci-attestation.yml"
    assert report["ci"]["dependency_lock"] == {
        "path": "config/d2_ci_requirements.lock",
        "sha256": hashlib.sha256((ROOT / "config/d2_ci_requirements.lock").read_bytes()).hexdigest(),
        "python": "3.11", "wheel_platform": "manylinux_2_17_x86_64",
    }
    for relative, digest in report["identities_sha256"].items():
        assert digest == hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    serialized = first.read_text(encoding="utf-8").lower()
    # Prohibition labels deliberately name forbidden evaluation modes, but the
    # artifact itself must never carry market data or a trading result.
    for forbidden in ("xauusd_h1.csv", "trade_count", "final_capital", "2023."):
        assert forbidden not in serialized


def test_ci_workflow_trigger_command_and_identity_inventory_are_locked_together():
    source = WORKFLOW.read_text(encoding="utf-8")
    module = runpy.run_path(str(SCRIPT))
    lock = ROOT / module["LOCK_PATH"]
    lock_lines = [line for line in lock.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    assert len(lock_lines) == 12
    assert all(re.fullmatch(r"[a-z0-9-]+==[^ ]+ --hash=sha256:[0-9a-f]{64}", line) for line in lock_lines)
    identities = set(module["IDENTITY_PATHS"])
    assert module["LOCK_PATH"] in identities
    assert "tests/test_research_v2_r3_h1_volatility_shock_d2_ci_provenance.py" in identities
    for path in identities:
        if path.startswith("tests/fixtures/research_v2_r3_h1_volatility_shock_"):
            assert "tests/fixtures/research_v2_r3_h1_volatility_shock_*" in source
        else:
            assert path in source
    for path in module["TEST_COMMAND"].split():
        if path.startswith("tests/"):
            assert path in source
    assert "tests/test_research_v2_r3_h1_volatility_shock_d2_ci_provenance.py" in source
