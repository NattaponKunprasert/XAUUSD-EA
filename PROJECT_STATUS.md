# Project status

## Current milestone

Isolate the active engine's intrabar stop/target resolution so Bid/Ask triggers, gap-through opens, and conservative same-bar ambiguity have one importable verified implementation.

## Verified inputs

- Initial simulated capital: USD 1,000
- Broker/account: XM Micro
- MT5 symbol: `GOLDmicro` (aliases shown by MT5: `XAUUSD`, `GOLD`)
- CSV/MT5 chart timestamps use the same broker-server clock
- CSV OHLC source: Bid
- M15 rows: 81,781
- M30 rows: 40,893
- H1 rows: 20,459
- H4 rows: 5,352
- No missing OHLCV cells, duplicate timestamps, backward timestamps, invalid OHLC relationships, or nonpositive volume were found
- M30, H1, and H4 aggregate exactly from M15, including volume
- The M15 smoke path now has deterministic long-only intrabar exit rules: gap-through-open exits at the open Bid, and same-bar stop/target conflicts resolve conservatively to the stop
- The M15 smoke path now returns a mark-to-market equity curve using realized cash plus open long PnL marked to the Bid close with XM Micro contract size
- The M15 smoke path now supports deterministic baseline/stress spread scenarios from `config/xm_micro_gold.json` and rejects unconfigured spread multipliers
- XM Micro point-based swap math is covered by an automated baseline test, including long/short values and Wednesday triple swap
- The M15 smoke path now force-closes any remaining open position at the final available Bid close so end-of-sample capital and trade logs are fully realized
- The deterministic single-position smoke path is now timeframe-parameterized and independently regression-tested on M15, M30, H1, and H4 using the same Bid/Ask execution, conservative intrabar exits, swap booking, and final-close accounting rules
- The importable validation layer now fail-fast plans chronological sample/holdout splits and walk-forward windows, with deterministic regression coverage on synthetic data plus real M15/M30/H1/H4 CSV boundaries
- Broker profile loading now fails loudly when verified XM Micro constants conflict, including the `GOLDmicro` symbol and contract size `1`
- Short-side Bid/Ask conversion, conservative same-bar SL/TP resolution, and risk-percent lot flooring are covered by deterministic accounting tests
- The deterministic baseline runner now supports an explicit short direction with next-bar Bid entry, Ask-based SL/TP and mark-to-market accounting, conservative same-bar conflicts, directional rollover swap, and forced final close; omitted direction remains long for backward-compatible fixed reports
- `python -m xauusd_ea.reporting` records the fixed M15 baseline/stress smoke run with data, broker-config, and code hashes; it does not use holdout data or rank candidates
- Local PowerShell bootstrap now detects a broken `.venv`, requires an explicit `-Recreate`, checks every subprocess exit code, and runs the test suite before reporting readiness
- The active notebook now routes AUTO sample/forward splits and walk-forward window planning through the importable validation helpers; unsafe WFA planning skips the candidate/timeframe instead of falling back to full-sample evaluation, and exact loaded configs record a validation fingerprint
- The active notebook now builds its runtime broker spec from `config/xm_micro_gold.json` and validates it before notebook-driven research paths run, preventing silent fallback to legacy XAUUSD contract, lot, spread, or commission defaults
- The active notebook now quantizes lots against the verified XM Micro min/max/step, skips sub-minimum risk sizes as no-trade, and removes legacy `contract_size=100` sizing/PnL fallbacks from active runtime helpers
- The active notebook now records `Research Config Fingerprint` values on sampled evaluation rows, rejects missing or mismatched persisted configs before exact forward/WFA runs, and regression-tests those fail-closed identity checks
- The active notebook now books swap by crossed broker-server rollover timestamps with no intraday charge, Wednesday triple swap, and weekend-skip handling, and the inspect/re-run notebook cell now refuses to auto-promote `SOFT` or generic fallback CSV exports
- Fibonacci extension targets now come from an importable closed-bar helper that uses only data through the signal bar, validates configured extension levels, and handles long/short direction explicitly; the isolated legacy path no longer contains an always-true level selector or reads levels from indicator parameters
- Next-bar entries now freeze ATR at the fully closed signal bar before deriving the stop and lot size; the active engine also defines its sizing bridge explicitly instead of depending on an undefined notebook-runtime helper
- The active engine now imports canonical MACD and Bollinger math, applies each frozen candidate's periods and multiplier, rejects invalid parameter sets, and has deterministic future-mutation coverage
- The active engine now imports canonical Wilder-smoothed ATR math, applies the frozen candidate period to stops, sizing, and volatility filters, rejects invalid or misaligned inputs, and has deterministic future-mutation coverage
- The active engine now imports canonical EMA math, applies each frozen candidate period, rejects invalid periods, and has deterministic future-mutation coverage
- The active engine now imports canonical Wilder-smoothed RSI math, applies each frozen candidate period, rejects invalid periods, and has deterministic future-mutation coverage
- The active engine now imports canonical Stochastic oscillator math, applies each frozen candidate k/d/smooth parameter set, rejects invalid or misaligned inputs, and has deterministic future-mutation coverage
- The active engine now imports canonical entry signal composition logic, preserving AND/OR/VOTE behavior and custom combo resolution while routing notebook wrappers through one tested helper
- The active engine now imports canonical entry filter routing logic, preserving enabled/disabled filter behavior, failing closed on unknown enabled filters, and applying filters at the already closed signal-bar index before next-bar entry
- The active engine now imports canonical strategy metric and cleaning helpers, preserving capped scoring for infinite profit factor, drawdown/loss-streak accounting, stopped-early detection, and strict trade/drawdown/win-rate cleaning gates
- The active engine now imports canonical execution-price and commission helpers, preserving Bid/Ask side mapping, audited baseline/stress spreads, adverse slippage, and verified zero commission while rejecting unknown slippage modes and broker-constant conflicts
- The active engine now imports canonical fixed, risk-percent, and ATR-based sizing, uses only the frozen entry ATR, floors volume to the verified XM Micro step, and treats sub-minimum sizes as no-trade without permitting broker-constant overrides
- The active engine now imports canonical direction-aware gross PnL for both mark-to-market and realized accounting, using only the verified XM Micro contract size instead of an undefined notebook-runtime helper
- The active engine now imports canonical mark-to-market equity accounting, preserving Bid/Ask liquidation, adverse slippage, verified zero commission, and XM Micro contract size `1`
- The active engine now imports canonical position-close accounting, preserving Bid/Ask exit execution, adverse slippage, single-booked swap and commission cash flows, and complete realized trade-ledger fields
- The active engine now imports canonical crossed-rollover swap booking, preserving directional verified broker rates, Wednesday triple swap, weekend skips, and exactly-once cash and position accumulation
- The active engine now imports canonical close-bar trailing-stop updates, preserving ATR, percent, and broker-point step behavior while preventing long/short stops from moving backward
- The active engine now imports canonical maximum-holding-bar exit timing, preserving disabled limits and exiting exactly when the configured number of completed holding bars is reached
- The active engine now imports canonical intrabar stop/target resolution, preserving Bid-triggered long exits, Ask-triggered short exits, actual gap-through bar-open execution in both supported execution modes, and conservative stop-first same-bar ambiguity
- Local verification on 2026-07-06 passed the targeted accounting/broker/validation suite plus `python -m pytest -q` on the conflict-resolved combined head: 97 tests passed in both runs
- Local verification on 2026-07-07 passed the focused accounting/baseline suite (45 tests) and full `python -m pytest -q` (103 tests) after adding the directional short smoke path
- Local verification on 2026-07-07 passed the focused Fibonacci/validation suite (47 tests) and full `python -m pytest -q` (109 tests) after isolating Fibonacci target behavior
- Local verification on 2026-07-07 passed the focused validation/exit suite (48 tests) and full `python -m pytest -q` (110 tests) after closing the entry-bar ATR leakage and adding a deterministic mutation regression
- Local verification on 2026-07-08 passed the focused indicator/validation suite (51 tests) and full `python -m pytest -q` (118 tests) after isolating candidate-sensitive MACD and Bollinger calculations
- Local verification on 2026-07-08 passed the focused indicator/validation suite (54 tests) and full `python -m pytest -q` (121 tests) after isolating the active engine's ATR calculation
- Local verification on 2026-07-08 passed the focused indicator/validation suite (57 tests) and full `python -m pytest -q` (124 tests) after isolating the active engine's EMA calculation
- Local verification on 2026-07-09 passed the focused indicator/validation suite (60 tests) and full `python -m pytest -q` (127 tests) after isolating the active engine's RSI calculation
- Local verification on 2026-07-09 passed the focused indicator/validation suite (66 tests) and full `python -m pytest -q` (133 tests) after isolating the active engine's Stochastic oscillator calculation
- Local verification on 2026-07-09 passed the focused entry/notebook-routing suite (5 tests) and full `python -m pytest -q` (138 tests) after isolating entry signal composition; pytest reported a Windows temp symlink cleanup permission warning after the passing run
- Local verification on 2026-07-09 passed the focused filter/notebook-routing suite (50 tests) and full `python -m pytest -q` (143 tests) after isolating entry filter routing; pytest reported a Windows temp symlink cleanup permission warning after the passing run
- Local verification on 2026-07-09 passed the focused metrics/notebook-routing suite (50 tests) and full `python -m pytest -q` (147 tests) after isolating strategy metrics and cleaning; pytest reported a Windows temp symlink cleanup permission warning after the passing run
- Local verification on 2026-07-10 passed the focused execution/notebook-routing suite (53 tests) and full `python -m pytest -q` (153 tests) after isolating execution-price and commission math; pytest reported the known Windows temp symlink cleanup permission warning after the passing run
- Local verification on 2026-07-10 passed the focused sizing/validation/accounting/broker/baseline suite (118 tests) and full `python -m pytest -q` (161 tests) after isolating active position sizing; pytest reported the known Windows temp symlink cleanup permission warning after both passing runs
- Local verification on 2026-07-11 passed the focused accounting/validation/baseline suite (100 tests) and full `python -m pytest -q` (168 tests) after isolating direction-aware gross PnL; pytest reported the known Windows temp symlink cleanup permission warning after both passing runs
- Local verification on 2026-07-11 passed the focused accounting/execution/validation/baseline suite (104 tests) and full `python -m pytest -q` (172 tests) after isolating mark-to-market equity; pytest reported the known Windows temp symlink cleanup permission warning after the passing full run
- Local verification on 2026-07-11 passed the focused accounting/execution/validation/baseline suite (109 tests) and full `python -m pytest -q` (177 tests) after isolating position-close accounting; pytest reported the known Windows temp-symlink cleanup permission warning after the passing full run
- Local verification on 2026-07-12 passed the focused accounting/validation/broker/baseline suite (124 tests) and full `python -m pytest -q` (180 tests) after isolating crossed-rollover swap booking; pytest reported the known Windows temp-symlink cleanup permission warning after the passing full run
- Local verification on 2026-07-12 passed the focused exit/validation/accounting/execution/baseline suite (121 tests) and full `python -m pytest -q` (184 tests) after isolating close-bar trailing-stop updates; pytest reported the known Windows temp-symlink cleanup permission warning after the passing full run
- Local verification on 2026-07-12 passed the focused exit/validation suite (68 tests) and full `python -m pytest -q` (192 tests) after isolating maximum-holding-bar exit timing; pytest reported the known Windows temp-symlink cleanup permission warning after the passing full run
- Local verification on 2026-07-12 passed the focused exit/execution/accounting/baseline/validation suite (136 tests) and full `python -m pytest -q` (199 tests) after fixing close-bar gap-through execution to use the actual OHLC open and validating execution modes fail closed; pytest reported the known Windows temp-symlink cleanup permission warning after the passing full run

## Broker facts

- Digits: 2
- Contract size: 1
- Tick size: 0.01
- Tick value: USD 0.01
- Floating spread
- Minimum/maximum/step volume: 0.10 / 100 / 0.01
- Commission: 0
- Fee: 0
- Swap is charged separately; Wednesday is the triple-swap day
- Current Python backtests model swap rollover at server-clock midnight and skip Saturday/Sunday midnights; the exact broker rollover cutover is an assumption until explicitly verified or configured

See `config/xm_micro_gold.json` for the machine-readable snapshot and bounded research variables.

## Research choices

- Risk per trade is a bounded candidate variable: 0.25%, 0.50%, 0.75%, or 1.00%
- Maximum positions is a candidate variable: 1, 2, or 3, but it must not be enabled until the engine supports and tests multiple positions correctly
- Hold overnight is a Boolean candidate variable
- Historical news filtering is disabled for now
- Normal spread baseline is 0.551142857 price units
- Stress scenarios use 1.5x and 2.0x the baseline spread

## Known immediate risks

- The newest backtest implementation must be isolated and tested before trusting results.
- A fixed average spread cannot reproduce the timing of historical spread spikes.
- Multi-position optimization is invalid until the backtest engine supports multiple concurrent positions.

## Readiness labels

- `compile-ready`: MQL5 compiles cleanly.
- `backtest-validated`: Python and MT5 tests pass the documented out-of-sample gates.
- `demo-forward-ready`: broker integration and safety controls are ready for a demo account.
- `live-ready`: requires satisfactory demo-forward evidence and an explicit user decision; it must never be inferred from backtests alone.
