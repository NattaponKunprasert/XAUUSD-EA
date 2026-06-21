# XAUUSD EA agent guidance

## Objective

Advance the repository toward one auditable XM Micro `GOLDmicro` EA. Correctness, leakage prevention, reproducibility, and risk controls take priority over headline profit.

## Read first

Before making changes, read:

1. `PROJECT_STATUS.md`
2. `XAUUSD_EA_Codex_Handoff.md`
3. `config/xm_micro_gold.json`
4. The active notebook and existing tests

## Non-negotiable rules

- Never use holdout or forward data to generate, tune, rank, or repair a candidate.
- Fit every adaptive parameter only inside its training window and freeze it before evaluation.
- Never fall back from holdout or walk-forward evaluation to full-sample evaluation. If a safe evaluation cannot run, fail or skip the candidate explicitly.
- Treat soft-ranked or fallback results as diagnostics only; never promote them when strict gates fail.
- Use Bid/Ask execution consistently. The CSV OHLC bars are Bid prices.
- For XM Micro `GOLDmicro`, use contract size `1`; never inherit the common XAUUSD default of `100`.
- Commission and fee are zero in the verified account history. Model swap separately.
- Treat `config/xm_micro_gold.json` as the single source of truth for verified broker/account constants. Fail loudly if an active path conflicts with it.
- Historical news filtering is disabled because no historical economic-calendar dataset is present.
- Do not use martingale, grid recovery, or averaging down.
- Keep aggregate open risk bounded when multi-position support is introduced.
- A calculated size below the broker minimum means no trade; never round upward beyond the configured risk limit.
- Do not claim profitability, live readiness, or production readiness from backtest results alone.
- Preserve user files and unrelated changes. Prefer small, reviewable commits.

## Execution order

1. Make a deterministic M15 smoke test pass with a tiny fixed configuration set. M15 is the first correctness baseline, not the final or only research timeframe.
2. Verify entry timing, intrabar SL/TP policy, spread, swap, sizing, PnL, and equity accounting.
3. Remove or isolate duplicate legacy definitions so cell order cannot change behavior.
4. Add automated tests before expanding the optimization grid.
5. Run equivalent deterministic smoke and accounting checks independently on M30, H1, and H4.
6. Validate sample/holdout boundaries and exact-forward configuration identity.
7. Only then run bounded per-timeframe optimization and walk-forward selection.
8. Add cross-timeframe signal dependencies only after every participating timeframe passes independently.
9. Freeze an accepted strategy and timeframe design before generating MQL5.

## Timeframe rules

- Design the engine to be timeframe-parameterized rather than maintaining separate behavior-changing implementations per timeframe.
- M15, M30, H1, and H4 may be researched independently after their correctness checks pass.
- Higher-timeframe signals may use only the last fully closed higher-timeframe bar available at the decision timestamp.
- Never expose an incomplete higher-timeframe candle to a lower-timeframe signal.
- Session logic, bars-per-day, holding duration, swap boundaries, and annualized metrics must be timeframe-aware.
- Select and freeze the trading timeframe or multi-timeframe design only inside the training process. Do not choose the best timeframe from holdout results.

## Engineering and audit rules

- Move production logic toward importable Python modules with one active definition per behavior. Use the notebook for orchestration and reporting, not competing implementations.
- Record each research run's data range and hash, code version, configuration hash, random seed, candidate count, cost profile, and explicit train/evaluation labels.
- Do not optimize risk percentage merely to maximize return. Choose risk from predefined safety constraints after strategy robustness is established.
- Do not add LLM trade decisions, news/sentiment logic, ML/RL, multi-position execution, or MQL5 export before the deterministic baselines and accounting tests pass.

## Required baseline tests

- Signal timing from a closed bar to the next permitted executable price.
- Bid/Ask handling for long and short entries and exits.
- Same-bar SL/TP ambiguity under an explicit conservative intrabar policy.
- Baseline and stress spread scenarios.
- Long and short swap, Wednesday triple swap, and overnight boundaries.
- Risk sizing, minimum volume, volume step, and contract size `1`.
- Realized PnL, floating equity, drawdown, and forced final close.
- Exact configuration identity between selection and forward evaluation.
- Chronological sample/holdout boundaries with no overlap.

## Promotion gates

Use these labels in order:

`research -> backtest-validated -> paper -> demo-forward -> eligible-for-live-review`

- Promotion requires explicit evidence and must never happen automatically.
- Backtest or paper results alone cannot authorize live trading.
- Calendar duration alone is insufficient; require adequate trade count, market coverage, acceptable drawdown, and zero unresolved accounting errors.

## Data and costs

- Input files are `XAUUSD_M15.csv`, `XAUUSD_M30.csv`, `XAUUSD_H1.csv`, and `XAUUSD_H4.csv`.
- Their mixed delimiter format is intentional: comma-separated header and tab-separated rows.
- The four timeframes have been verified to aggregate exactly from M15.
- Use the baseline and stress spreads recorded in `config/xm_micro_gold.json`.
- Mutable broker properties must eventually be read dynamically by the MQL5 EA.

## Verification

Run the narrowest relevant checks after each change. Once tests exist, the default command is:

```bash
python -m pytest -q
```

Do not launch the full optimization grid merely to verify a code edit.
