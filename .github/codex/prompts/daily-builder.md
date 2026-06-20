# XAUUSD EA daily builder

Read `AGENTS.md`, `PROJECT_STATUS.md`, `XAUUSD_EA_Codex_Handoff.md`, `config/xm_micro_gold.json`, the active source code, tests, and recent repository history before acting.

Advance exactly one bounded engineering milestone toward one auditable XM Micro `GOLDmicro` EA. Select the highest-priority incomplete milestone that can be completed safely in this run. Prefer correctness, leakage prevention, deterministic tests, and broker-accurate execution over strategy performance.

## Per-run limits

- Work on one coherent problem group only.
- Keep the change small and reviewable.
- Do not merge pull requests or modify GitHub settings.
- Do not run or materialize the full optimization grid.
- Do not start long optimization or walk-forward jobs unless the repository explicitly marks that bounded run as the next approved milestone.
- Do not add multi-position optimization before concurrent-position accounting is implemented and tested.
- Do not use holdout or forward data to generate, tune, rank, or repair candidates.
- Historical news filtering remains disabled until an appropriate historical calendar dataset exists.
- Never claim profitability, live readiness, or production readiness from backtests alone.

## Required workflow

1. Inspect the current implementation and tests. State the chosen milestone in your reasoning before editing.
2. Implement the smallest complete change that advances that milestone.
3. Add or strengthen focused deterministic tests that fail without the change.
4. Run the narrowest relevant tests. Run `python -m pytest -q` before finishing when feasible within the time limit.
5. Update `PROJECT_STATUS.md` only when the verified project state or next milestone materially changes.
6. Leave the working tree with only intentional source, test, configuration, or documentation changes. Do not commit generated outputs, caches, large optimization results, credentials, or screenshots.
7. In the final response, report the chosen milestone, files changed, tests and results, correctness risks, blockers, and the recommended next milestone.

If a required decision depends on user risk preferences, real-money authorization, missing broker facts, MT5 access, or unavailable data, do not guess. Make no speculative strategy change; report the blocker and stop.