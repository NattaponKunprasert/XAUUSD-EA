# XAUUSD EA daily builder

Read `AGENTS.md`, `PROJECT_STATUS.md`, `XAUUSD_EA_Codex_Handoff.md`, `config/xm_micro_gold.json`, the active source code, tests, and recent repository history before acting.

Advance one bounded engineering milestone toward one auditable XM Micro `GOLDmicro` EA. A milestone may include up to three tightly coupled unfinished subtasks when they share the same correctness objective and can be completed and verified safely in this run. Select the highest-priority incomplete milestone. Prefer correctness, leakage prevention, deterministic tests, and broker-accurate execution over strategy performance.

## Per-run limits

- Work on one coherent problem group only; combine no more than three tightly coupled subtasks.
- Keep the change small and reviewable: no more than 6 changed files and 400 changed lines. If the complete milestone would exceed either limit, finish a smaller coherent slice instead.
- Do not push, merge pull requests, or modify GitHub settings; the workflow owns publication and merge policy.
- Do not run or materialize the full optimization grid.
- Do not start long optimization or walk-forward jobs unless the repository explicitly marks that bounded run as the next approved milestone.
- Do not add multi-position optimization before concurrent-position accounting is implemented and tested.
- Do not use holdout or forward data to generate, tune, rank, or repair candidates.
- Historical news filtering remains disabled until an appropriate historical calendar dataset exists.
- Never claim profitability, live readiness, or production readiness from backtests alone.

## Required workflow

1. Inspect the current implementation and tests. State the chosen milestone in your reasoning before editing.
2. Implement the largest complete coherent slice that fits the per-run limits. Do not stop after the first tiny edit when adjacent implementation and regression tests are required to complete the same milestone.
3. Add or strengthen focused deterministic tests that fail without the change.
4. Run the narrowest relevant tests. Run `python -m pytest -q` before finishing when feasible within the time limit.
5. Update `PROJECT_STATUS.md` only when the verified project state or next milestone materially changes.
6. Leave the working tree with only intentional source, test, configuration, or documentation changes. Do not commit generated outputs, caches, large optimization results, credentials, or screenshots.
7. Return the required structured final result. Set `merge_recommended` to `true` only when the change is complete, focused, tests pass, no blocker remains, and the risk is genuinely low. Otherwise set it to `false`. Use `risk_level: low` only for a small, deterministic, well-tested change that does not alter workflow security, broker facts, dependencies, datasets, optimization boundaries, or live-trading authorization.

If a required decision depends on user risk preferences, real-money authorization, missing broker facts, MT5 access, or unavailable data, do not guess. Make no speculative strategy change; report the blocker, set `merge_recommended` to `false`, and stop.
