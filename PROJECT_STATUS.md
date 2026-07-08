# Project status

## Current milestone

Isolate the active engine's candidate-sensitive indicator math so MACD and Bollinger calculations are importable, deterministic, and tied to each frozen candidate configuration.

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
- Local verification on 2026-07-06 passed the targeted accounting/broker/validation suite plus `python -m pytest -q` on the conflict-resolved combined head: 97 tests passed in both runs
- Local verification on 2026-07-07 passed the focused accounting/baseline suite (45 tests) and full `python -m pytest -q` (103 tests) after adding the directional short smoke path
- Local verification on 2026-07-07 passed the focused Fibonacci/validation suite (47 tests) and full `python -m pytest -q` (109 tests) after isolating Fibonacci target behavior
- Local verification on 2026-07-07 passed the focused validation/exit suite (48 tests) and full `python -m pytest -q` (110 tests) after closing the entry-bar ATR leakage and adding a deterministic mutation regression
- Local verification on 2026-07-08 passed the focused indicator/validation suite (51 tests) and full `python -m pytest -q` (118 tests) after isolating candidate-sensitive MACD and Bollinger calculations

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
