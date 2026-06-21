# Project status

## Current milestone

Prepare and verify a small M15-only baseline that exercises the active backtest implementation, including deterministic conservative intrabar exits and equity accounting, without invoking the full parameter grid.

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
- XM Micro point-based swap math is covered by an automated baseline test, including long/short values and Wednesday triple swap

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

See `config/xm_micro_gold.json` for the machine-readable snapshot and bounded research variables.

## Research choices

- Risk per trade is a bounded candidate variable: 0.25%, 0.50%, 0.75%, or 1.00%
- Maximum positions is a candidate variable: 1, 2, or 3, but it must not be enabled until the engine supports and tests multiple positions correctly
- Hold overnight is a Boolean candidate variable
- Historical news filtering is disabled for now
- Normal spread baseline is 0.551142857 price units
- Stress scenarios use 1.5x and 2.0x the baseline spread

## Known immediate risks

- The notebook contains legacy and newer duplicate function definitions.
- A legacy Fibonacci function still contains an always-true condition.
- The newest backtest implementation must be isolated and tested before trusting results.
- The original generic XAUUSD default contract size of 100 is invalid for this XM Micro account.
- A fixed average spread cannot reproduce the timing of historical spread spikes.
- Multi-position optimization is invalid until the backtest engine supports multiple concurrent positions.

## Readiness labels

- `compile-ready`: MQL5 compiles cleanly.
- `backtest-validated`: Python and MT5 tests pass the documented out-of-sample gates.
- `demo-forward-ready`: broker integration and safety controls are ready for a demo account.
- `live-ready`: requires satisfactory demo-forward evidence and an explicit user decision; it must never be inferred from backtests alone.
