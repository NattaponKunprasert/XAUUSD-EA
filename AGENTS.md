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
- Do not silently fall back from a holdout-safe path to an in-sample path.
- Use Bid/Ask execution consistently. The CSV OHLC bars are Bid prices.
- For XM Micro `GOLDmicro`, use contract size `1`; never inherit the common XAUUSD default of `100`.
- Commission and fee are zero in the verified account history. Model swap separately.
- Historical news filtering is disabled because no historical economic-calendar dataset is present.
- Do not use martingale, grid recovery, or averaging down.
- Keep aggregate open risk bounded when multi-position support is introduced.
- Do not claim profitability, live readiness, or production readiness from backtest results alone.
- Preserve user files and unrelated changes. Prefer small, reviewable commits.

## Execution order

1. Make a deterministic M15-only smoke test pass with a tiny fixed configuration set.
2. Verify entry timing, intrabar SL/TP policy, spread, swap, sizing, PnL, and equity accounting.
3. Remove or isolate duplicate legacy definitions so cell order cannot change behavior.
4. Add automated tests before expanding the optimization grid.
5. Validate sample/holdout boundaries and exact-forward configuration identity.
6. Only then run bounded optimization and walk-forward selection.
7. Freeze an accepted strategy before generating MQL5.

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
