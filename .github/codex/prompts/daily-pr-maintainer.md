# XAUUSD EA daily PR maintainer

Read `AGENTS.md`, `PROJECT_STATUS.md`, `XAUUSD_EA_Codex_Handoff.md`, `config/xm_micro_gold.json`, the active source code, tests, recent history, and the complete diff from `main...HEAD` before acting.

You are maintaining an existing open daily-agent pull request. Do not start a new milestone. Make the existing PR complete, internally consistent, and safe to integrate.

## Required workflow

1. Inspect every changed file and test in `main...HEAD`.
2. Identify and resolve correctness risks, incomplete integration, stale assumptions, merge conflicts, and any reason the previous run withheld its merge recommendation.
3. Preserve all non-negotiable leakage, broker-accounting, reproducibility, risk, and no-live-authorization rules in `AGENTS.md`.
4. Add or strengthen deterministic regression tests for each correction. For configuration identity guards, runtime metadata exemptions must be narrowly scoped and must never hide nested research parameters.
5. Keep the complete PR within 6 changed files and 400 changed lines when possible. If the existing PR is already near the limit, prefer a focused correction over unrelated expansion.
6. Run the narrowest relevant tests and then `python -m pytest -q`.
7. Return the required structured final result. Set `merge_recommended` to `true` when the existing PR is coherent, all tests pass, no blocker remains, and you judge it safe to integrate. Risk may be `low` or `medium`; use `high` only for unresolved material risk and keep `merge_recommended` false in that case.
8. If the PR cannot be made safe in this run, make only safe progress, explain the remaining blocker precisely, and leave `merge_recommended` false so the next scheduled run can continue repairing the same PR.

Do not push, merge pull requests, modify GitHub settings, authorize live trading, run the full optimization grid, or claim profitability/readiness. The workflow owns publication and the final merge action.
