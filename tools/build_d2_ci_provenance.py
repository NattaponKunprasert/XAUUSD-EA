"""Build bounded, canonical provenance input for the Round-3 H1 D2 CI job.

This program does not run a strategy or read market data.  It records only
source/test identities and declared GitHub Actions context.  GitHub's remote
artifact attestation, not this local JSON file, is the external authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
WORKFLOW_PATH = ".github/workflows/xauusd-d2-ci-attestation.yml"
LOCK_PATH = "config/d2_ci_requirements.lock"
TEST_COMMAND = (
    "python -B -m pytest -q --cache-clear "
    "tests/test_research_v2_r3_h1_volatility_shock_d2_ci_provenance.py "
    "tests/test_research_v2_r3_h1_volatility_shock_d1.py "
    "tests/test_research_v2_r3_h1_volatility_shock_d1_evidence_oracle.py "
    "tests/test_research_v2_r3_h1_volatility_shock_d2.py "
    "tests/test_research_v2_r3_h1_volatility_shock_d2_evidence_oracle.py "
    "tests/test_broker_profile_runtime.py tests/test_accounting_extensions.py"
)
IDENTITY_PATHS = (
    "xauusd_ea/research_v2_volatility_shock_d2.py",
    "xauusd_ea/research_v2_volatility_shock_d1.py",
    "xauusd_ea/d2_runtime_primitives.py",
    "config/xm_micro_gold.json",
    # D1 authenticates these fixed prior-stage records before it can bind the
    # H1 prefix.  CI must version their exact bytes rather than accidentally
    # inheriting them from an otherwise unrelated local research worktree.
    "config/research_v2_d0_agenda.json",
    "config/research_v2_d0_audit_evidence.json",
    "config/research_v2_r2_m30_regime_direction_d3_audit_evidence.json",
    "config/research_v2_r3_h1_volatility_shock_d1_contract.json",
    "config/research_v2_r3_h1_volatility_shock_d1_audit_evidence.json",
    "config/research_v2_r3_h1_volatility_shock_d2_audit_evidence.json",
    "tests/test_research_v2_r3_h1_volatility_shock_d1.py",
    "tests/test_research_v2_r3_h1_volatility_shock_d1_evidence_oracle.py",
    "tests/test_research_v2_r3_h1_volatility_shock_d2.py",
    "tests/test_research_v2_r3_h1_volatility_shock_d2_evidence_oracle.py",
    "tests/fixtures/research_v2_r3_h1_volatility_shock_d1_expected.json",
    "tests/fixtures/research_v2_r3_h1_volatility_shock_d2_expected.json",
    "tests/fixtures/research_v2_r3_h1_volatility_shock_d2_oracle.json",
    "tests/test_research_v2_r3_h1_volatility_shock_d2_ci_provenance.py",
    LOCK_PATH,
    WORKFLOW_PATH,
)
PROHIBITIONS = {
    "no_market_prices_or_csv": True,
    "no_d3_or_candidates": True,
    "no_selection_test_holdout_forward_or_full_sample": True,
    "no_notebook_mql5_deployment_or_promotion": True,
}


def _relative_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or relative not in IDENTITY_PATHS:
        raise ValueError("unapproved provenance identity path")
    target = (root / relative).resolve()
    if target.parent != root.resolve() and root.resolve() not in target.parents:
        raise ValueError("provenance path escaped repository")
    if target.is_symlink() or not target.is_file():
        raise ValueError(f"provenance identity unavailable: {relative}")
    return target


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_report(root: Path, *, commit_sha: str, repository: str, run_id: str,
                 run_attempt: str, server_url: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ValueError("commit SHA must be exactly 40 lowercase hexadecimal characters")
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repository):
        raise ValueError("repository must be owner/name")
    if not run_id.isdecimal() or not run_attempt.isdecimal() or not re.fullmatch(r"https://[^\s]+", server_url):
        raise ValueError("CI run context is malformed")
    identities = {
        relative: _sha256(_relative_file(root, relative))
        for relative in IDENTITY_PATHS
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": "research_v2_r3_h1_volatility_shock_d2_ci_provenance",
        "attestation_status": "PENDING_CI_ATTESTATION",
        "promotion_label": "research",
        "ci": {
            "provider": "github-actions",
            "repository": repository,
            "commit_sha": commit_sha,
            "workflow_path": WORKFLOW_PATH,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "run_url": f"{server_url}/{repository}/actions/runs/{run_id}",
            "dependency_lock": {
                "path": LOCK_PATH,
                "sha256": identities[LOCK_PATH],
                "python": "3.11",
                "wheel_platform": "manylinux_2_17_x86_64",
            },
        },
        "identities_sha256": identities,
        "test": {"command": TEST_COMMAND, "status": "passed"},
        "scope_prohibitions": PROHIBITIONS,
        "external_authority_limit": (
            "This JSON is not an attestation. It becomes externally attributable "
            "only after GitHub verifies the artifact attestation against this "
            "repository, commit, and workflow."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--server-url", required=True)
    args = parser.parse_args()
    report = build_report(args.root.resolve(), commit_sha=args.commit_sha,
                          repository=args.repository, run_id=args.run_id,
                          run_attempt=args.run_attempt, server_url=args.server_url)
    args.output.write_bytes(json.dumps(report, allow_nan=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8") + b"\n")


if __name__ == "__main__":
    main()
