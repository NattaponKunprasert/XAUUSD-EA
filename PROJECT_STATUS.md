# Project status

## Current milestone

Clear the remaining active-notebook audit blockers around exact-forward identity, rollover-based swap accounting, and fail-closed `CLEAN`-only inspection before any broader notebook-driven research milestone resumes.

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
- The active notebook now routes AUTO sample/forward splits and walk-forward window planning through the importable validation helpers; unsafe WFA planning skips the candidate/timeframe instead of falling back to full-sample evaluation, and exact loaded configs record a validation fingerprint
- The active notebook now builds its runtime broker spec from `config/xm_micro_gold.json` and validates it before notebook-driven research paths run, preventing silent fallback to legacy XAUUSD contract, lot, spread, or commission defaults
- The active notebook now quantizes lots against the verified XM Micro min/max/step, skips sub-minimum risk sizes as no-trade, and removes legacy `contract_size=100` sizing/PnL fallbacks from active runtime helpers
- The active notebook now records `Research Config Fingerprint` values on sampled evaluation rows, rejects missing or mismatched persisted configs before exact forward/WFA runs, and regression-tests those fail-closed identity checks
- The active notebook now books swap by crossed broker-server rollover timestamps with no intraday charge, Wednesday triple swap, and weekend-skip handling, and the inspect/re-run notebook cell now refuses to auto-promote `SOFT` or generic fallback CSV exports

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

- A legacy Fibonacci function still contains an always-true condition.
- The newest backtest implementation must be isolated and tested before trusting results.
- A fixed average spread cannot reproduce the timing of historical spread spikes.
- Multi-position optimization is invalid until the backtest engine supports multiple concurrent positions.

## Readiness labels

- `compile-ready`: MQL5 compiles cleanly.
- `backtest-validated`: Python and MT5 tests pass the documented out-of-sample gates.
- `demo-forward-ready`: broker integration and safety controls are ready for a demo account.
- `live-ready`: requires satisfactory demo-forward evidence and an explicit user decision; it must never be inferred from backtests alone.
