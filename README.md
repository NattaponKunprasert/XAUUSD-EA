# XAUUSD EA

Research and engineering project for producing one XM Micro `GOLDmicro` Expert Advisor from an auditable Python backtest and walk-forward validation pipeline.

## Current state

- Source notebook: `EA_XAUUSD_29102025_Master_FIXED_V3_9_HOLDOUT_SAFE_EXACT_FORWARD (1).ipynb`
- Handoff and known issues: `XAUUSD_EA_Codex_Handoff.md`
- Input data: MT5 Bid OHLCV for M15, M30, H1, and H4 from 2023-01-03 through 2026-06-19
- Immediate milestone: connect the active notebook to the audited validation helpers without changing the verified M15/M30/H1/H4 smoke baseline

This repository is research software. No strategy should be described as profitable or live-ready until it has passed the documented validation and demo-forward gates.

## Broker baseline

The target account is XM Micro and the actual MT5 symbol is `GOLDmicro`. The verified broker snapshot and bounded optimization inputs live in `config/xm_micro_gold.json`.

Important differences from a standard XAUUSD contract:

- contract size: `1`, not `100`
- tick size: `0.01`
- minimum volume: `0.10`
- floating spread baseline: approximately `0.551142857` price units (`55.1142857` points)
- commission and fee: `0`

The future MQL5 EA must read mutable symbol properties from MT5 at runtime rather than assuming the snapshot never changes.

## Local setup (Windows PowerShell)

Python 3.12 is the repository/CI reference runtime. From the repository root:

```powershell
.\scripts\setup_local.ps1
```

If an old virtual environment points to a missing Python installation, rebuild it explicitly:

```powershell
.\scripts\setup_local.ps1 -Recreate
```

Run the regression suite and write an auditable deterministic smoke report with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m xauusd_ea.reporting
```

The generated report is written under `outputs/`, which is intentionally excluded from Git.

### Git audit trail

Use a real clone of `NattaponKunprasert/XAUUSD-EA`; do not initialize an unrelated history. Every reviewable change should use a branch based on `origin/main` and record the test command in its pull request.

## Cloud setup

Scheduled Cloud Agent runs are disabled. The workflow retains manual dispatch only for an explicit future decision. The notebook resolves CSV files from the repository root when it is not running in Google Colab.

Suggested first task:

```text
Read AGENTS.md, PROJECT_STATUS.md, XAUUSD_EA_Codex_Handoff.md, and the notebook. Build a small M15-only baseline smoke test. Do not run the full optimization grid. Verify broker math using config/xm_micro_gold.json and report any correctness blockers before changing strategy logic.
```

## Validation stages

1. Backtest-engine correctness and deterministic smoke tests
2. Leakage-safe sample/holdout and rolling out-of-sample validation
3. Stress testing across spread and execution assumptions
4. Strategy selection and frozen configuration export
5. MQL5 implementation and Python/MT5 parity checks
6. Demo forward test before any live-use decision
