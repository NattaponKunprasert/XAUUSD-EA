# XAUUSD EA / Strategy Optimizer — Codex Handoff Brief

## Project Goal

This project is a Python Notebook prototype for building, testing, and selecting trading strategies for **XAUUSD** using OHLCV data exported from MetaTrader 5.

The system generates many strategy configurations from technical indicators, entry logic, exit logic, sizing methods, trading filters, and cost assumptions. It then backtests those configurations, ranks them by performance, validates them through walk-forward testing, and exports the best strategies for possible conversion into an MQL5 Expert Advisor later.

Main source file:

```text
EA XAUUSD_24072025_Master.ipynb
```

---

## Current High-Level Architecture

The notebook currently contains these main parts:

1. MT5 CSV data loading
2. Indicator parameter grids
3. Indicator precomputation
4. Long and short entry logic
5. Exit logic
6. Position sizing
7. Trading cost / friction model
8. Entry filters
9. Strategy config generator
10. Backtest engine
11. Strategy metrics and scoring
12. Strategy filtering and deduplication
13. Walk-forward validation
14. Export utilities

---

## Data Loading

The project loads OHLCV CSV files exported from MetaTrader 5.

Expected fields:

```text
Time, Open, High, Low, Close, Volume
```

Main function:

```python
load_mt5_csv(filepath)
```

Current issue:

Some file paths are hard-coded, for example Windows MT5 paths or Google Drive paths.

Recommended fix:

Core functions should not contain hard-coded local paths. Move paths into config, CLI arguments, environment variables, or notebook-level variables.

---

## Indicator Parameter Grids

There are two main parameter groups:

### `typical_params`

Used as standard/default indicator settings.

Examples:

```python
EMA 12 / 26
RSI 14
MACD 12 / 26 / 9
Bollinger Bands 20 / 2.0
ATR 14
Stochastic 14 / 3
```

### `indicator_params`

Used for optimization grid generation.

Examples:

```python
EMA fast: 5-25
EMA slow: 30-200
RSI period: 7-21
MACD fast: 8-16
MACD slow: 20-30
MACD signal: 6-12
BB period: 10-30
BB stddev: 1.5-3.0
ATR period: 10-20
ATR multiplier: 1.0-3.5
Stochastic k: 10-20
Stochastic d: 3-5
```

These are merged into:

```python
combined_params
```

---

## Indicator Precomputation

Main function:

```python
precompute_indicators(df, combined_params)
```

It precomputes:

- EMA
- RSI
- MACD
- Bollinger Bands
- ATR
- Stochastic
- Fibonacci support/resistance

### Critical issue

The function requires `combined_params`, but later code calls it without the second argument:

```python
precompute_indicators(DF_M15.copy())
```

Recommended fix:

Either always call:

```python
precompute_indicators(DF_M15.copy(), combined_params)
```

or make `combined_params` optional:

```python
def precompute_indicators(df, combined_params=None):
    if combined_params is None:
        combined_params = globals()["combined_params"]
```

---

## Entry Logic

There are long and short entry functions.

### Long entry functions

```python
ema_entry
rsi_entry
macd_entry
bb_entry
fib_entry
stoch_entry
```

### Short entry functions

```python
ema_short_entry
rsi_short_entry
macd_short_entry
bb_short_entry
fib_short_entry
stoch_short_entry
```

Composite entry function:

```python
generate_entry_condition(indicators, params, direction="long", mode="AND")
```

Default logic uses `AND`, meaning all indicators in a strategy combination must signal at the same time.

---

## Exit Logic

Main exit functions:

```python
calculate_atr_stop
calculate_tp_by_rr
calculate_structure_stop
calculate_fib_target
generate_exit_levels
calculate_trailing_stop
check_max_holding
indicator_reversal
check_drawdown_breach
```

Supported exit types:

- ATR stop loss
- Structure stop loss
- Risk/reward take profit
- Fibonacci target
- ATR trailing stop
- Percent trailing stop
- Step trailing stop
- Max holding bars
- Indicator reversal exit
- Drawdown breach exit

---

## Position Sizing

Main function:

```python
calculate_position_size()
```

Supported sizing methods:

```text
fixed
risk_percent
atr_based
```

Current default examples:

```python
fixed lot = 0.1
risk_percent = 1.0
atr_based = base_lot_size 0.1, atr_multiplier 1.5
```

### Critical issue

`atr_based` sizing needs the current ATR value, but `run_backtest()` does not consistently inject `current_atr` into the sizing config.

Recommended fix inside `run_backtest()` before calling sizing:

```python
sizing_config = config["sizing"].copy()
sizing_config["atr"] = current_atr
lot = calculate_position_size(..., sizing_config=sizing_config)
```

---

## Trading Cost / Friction Model

Main functions:

```python
apply_slippage
apply_commission
apply_spread
apply_swap_cost
compute_trade_costs
```

Current config examples:

```python
slippage fixed = 1.0
spread_points = 1.5
commission_per_lot = 7.0
swap_per_lot = -1.0
bars_per_day = 96
```

### Critical issue

`run_backtest()` passes `"long"` / `"short"` into `compute_trade_costs()`, but cost functions check for `"buy"` / `"sell"`.

This causes incorrect slippage/spread handling.

Correct mapping:

```text
long entry  = buy
long exit   = sell
short entry = sell
short exit  = buy
```

Recommended fix:

Create a helper:

```python
def order_side_for_cost(position_direction, action):
    if position_direction == "long" and action == "entry":
        return "buy"
    if position_direction == "long" and action == "exit":
        return "sell"
    if position_direction == "short" and action == "entry":
        return "sell"
    if position_direction == "short" and action == "exit":
        return "buy"
    raise ValueError(f"Invalid position_direction/action: {position_direction}/{action}")
```

---

## Trade Filters

Main filters:

```python
trend_filter
volatility_filter
volume_filter
session_filter
time_filter
```

Filter wrapper:

```python
passes_all_filters()
```

Filter registry:

```python
entry_filters = {
    "trend_filter": trend_filter,
    "volatility_filter": volatility_filter,
    "volume_filter": volume_filter,
    "session_filter": session_filter,
    "time_filter": time_filter,
}
```

Strategy configs may include 0 to N filters.

---

## Strategy Config Generator

Main function:

```python
generate_all_strategy_configs()
```

It generates strategies from combinations of:

- Indicator sets
- Indicator parameters
- Stop loss settings
- Take profit settings
- Trailing stop settings
- Time-based exits
- Position sizing methods
- Friction assumptions
- Entry filters
- Strategy UID/hash

### Critical issue

The grid can become extremely large.

The function currently risks materializing huge product sets in memory.

Recommended fixes:

- Use lazy iterators
- Add `max_configs`
- Add `batch_size`
- Add sampling mode
- Avoid `list(itertools.product(...))` for large grids
- Keep full-grid generation optional

---

## Backtest Engine

Main function:

```python
run_backtest(config, df, initial_capital=10000.0)
```

Current flow:

1. Iterate through bars
2. If no open position:
   - Check long/short entry signal
   - Apply filters
   - Generate SL/TP
   - Calculate position size
   - Apply entry costs
   - Open position
3. If position exists:
   - Update trailing stop
   - Check TP / SL / time exit / reversal exit
   - Apply exit costs
   - Calculate PnL
   - Update capital
   - Store trade
4. Return:

```python
trades, final_capital, equity_curve
```

### Important issue

PnL currently uses hard-coded contract size:

```python
pnl = price_diff * lot * 100
```

For XAUUSD, `100` may represent 1 standard lot = 100 oz, but this should be configurable.

Recommended fix:

```python
contract_size = config.get("contract_size", 100)
pnl = price_diff * lot * contract_size
```

or:

```python
contract_size = config["sizing"].get("contract_size", 100)
```

---

## Metrics and Scoring

There are two metric/evaluation systems.

### Basic evaluation

Functions:

```python
evaluate_strategy()
filter_strategies()
rank_strategies()
```

Metrics include:

```text
net_profit
win_rate
profit_factor
expectancy
sharpe
max_drawdown
trade_count
score
```

Example scoring formula:

```python
net_profit - max_drawdown * 1000 + sharpe * 100 + profit_factor * 50
```

### More detailed evaluation

Functions:

```python
compute_strategy_metrics()
evaluate_backtest_configs()
```

Metrics include:

```text
Net Profit
CAGR
Max Drawdown
Volatility
Sharpe Ratio
Sortino Ratio
Win Rate
Profit Factor
# Trades
Avg Trade Duration
Expectancy
Recovery Factor
Max Consecutive Losses
Strategy Score
```

Potential issue:

If a strategy has no losing trades, `profit_factor` may become infinite and distort ranking.

Recommended fix:

Cap or normalize `profit_factor`, for example:

```python
profit_factor_for_score = min(profit_factor, 10)
```

---

## Walk-Forward Validation

Main functions:

```python
split_walk_forward_windows
run_training_loop
select_top_strategies
validate_on_test_set
aggregate_results
run_full_walk_forward
```

Current example config:

```python
wf_config = {
    "train_window": 2000,
    "test_window": 500,
    "step_size": 500,
    "top_n_strategies": 3,
}
```

Flow:

1. Split data into train/test windows
2. Run strategies on train window
3. Select top strategies
4. Validate selected strategies on test window
5. Aggregate results

---

## Strategy Cleaning and Deduplication

Main functions:

```python
clean_strategies
deduplicate_strategies
filter_valid_strategies
```

Common filters:

```text
minimum trade count
maximum drawdown
maximum win rate cap
equity curve correlation deduplication
```

Example defaults:

```python
min_trades = 30
max_mdd = 0.3
win_rate_cap = 0.95
dedup_threshold = 0.99
```

Purpose:

Avoid selecting strategies that are overfit, unrealistic, or duplicates of each other.

---

## Export Utilities

Main functions:

```python
export_top_strategies
plot_equity_curve
export_strategy_config
unified_strategy_comparison
```

Export formats:

```text
CSV
JSON
PKL
```

The JSON strategy config is intended to become the bridge toward future MQL5 EA generation.

---

# Critical Issues To Fix First

## 1. `precompute_indicators()` call mismatch

Definition:

```python
precompute_indicators(df, combined_params)
```

Later call:

```python
precompute_indicators(DF_M15.copy())
```

Fix:

```python
precompute_indicators(DF_M15.copy(), combined_params)
```

or add a default fallback.

---

## 2. `evaluate_backtest_configs()` interface mismatch

Current definition:

```python
def evaluate_backtest_configs(configs, df, initial_capital=10000):
```

Later call:

```python
evaluate_backtest_configs(
    batch_configs,
    data_dict,
    initial_capital=initial_capital,
    multi_timeframe=True,
)
```

Problems:

- Function does not accept `multi_timeframe`
- Function expects one DataFrame, not a dict
- `run_backtest()` also expects one DataFrame

Recommended fix:

Either split into:

```python
evaluate_backtest_configs_single_tf(configs, df, ...)
evaluate_backtest_configs_multi_tf(configs, data_dict, ...)
```

or let one function detect input type:

```python
if isinstance(data, pd.DataFrame):
    run single-timeframe
elif isinstance(data, dict):
    run multi-timeframe
```

For now, it is acceptable to temporarily disable multi-timeframe mode with a clear TODO, as long as the single-timeframe pipeline runs end-to-end.

---

## 3. Direction mapping bug in cost model

Current issue:

`run_backtest()` passes `"long"` / `"short"` to cost functions that expect `"buy"` / `"sell"`.

Correct mapping:

```text
long entry  = buy
long exit   = sell
short entry = sell
short exit  = buy
```

This should be fixed before trusting backtest results.

---

## 4. ATR-based sizing does not receive ATR

Fix by injecting `current_atr` into sizing config before calling `calculate_position_size()`.

---

## 5. Fibonacci target bug

There is logic like:

```python
if m in fib_levels or True
```

This is always true.

Also, `run_backtest()` appears to call Fibonacci target logic using:

```python
config["params"].get("Fibonacci", {})
```

But Fibonacci TP levels should come from:

```python
config["exit"]["fib_levels"]
```

Fix this and make the function testable.

---

## 6. MACD optimization parameters are not actually used

Current issue:

`macd_entry()` uses a default column like:

```python
macd_histogram
```

But the parameter grid includes many MACD fast/slow/signal combinations.

Recommended fix:

Precompute dynamic MACD columns:

```python
macd_hist_{fast}_{slow}_{signal}
macd_line_{fast}_{slow}_{signal}
macd_signal_{fast}_{slow}_{signal}
```

Then entry logic should read the columns matching the strategy config.

---

## 7. Bollinger Band optimization parameters are not actually used

Current issue:

`bb_entry()` reads default columns:

```python
bb_lower
bb_upper
```

But the parameter grid includes different period/stddev values.

Recommended fix:

Precompute dynamic BB columns:

```python
bb_lower_{period}_{stddev}
bb_upper_{period}_{stddev}
bb_mid_{period}_{stddev}
```

Then entry logic should read the columns matching the strategy config.

---

## 8. PnL contract size is hard-coded

Current issue:

```python
price_diff * lot * 100
```

Recommended fix:

```python
contract_size = config.get("contract_size", 100)
pnl = price_diff * lot * contract_size
```

---

## 9. Grid explosion risk

Recommended fix:

- Do not materialize full parameter products into lists
- Add `max_configs`
- Add `batch_size`
- Add random sampling mode
- Make full grid optional

---

## 10. Hard-coded paths

Move data paths out of core functions.

---

# Recommended Codex Work Plan

## Phase 1 — Make the notebook run end-to-end

Acceptance criteria:

```text
[ ] Small M15-only test run completes without exception
[ ] `precompute_indicators` works
[ ] `generate_all_strategy_configs` can produce a tiny grid
[ ] `run_backtest` returns trades/final_capital/equity_curve
[ ] `evaluate_backtest_configs` returns a DataFrame or clear empty result
[ ] No multi-timeframe error blocks the small test run
```

---

## Phase 2 — Fix correctness issues

Acceptance criteria:

```text
[ ] Cost direction mapping is fixed
[ ] ATR-based sizing receives ATR
[ ] Fibonacci target logic no longer has always-true condition
[ ] PnL contract size is configurable
[ ] MACD params used in actual logic
[ ] Bollinger params used in actual logic
[ ] Infinite profit factor does not distort scoring
```

---

## Phase 3 — Add smoke tests

Add tests for:

```text
[ ] indicator precompute
[ ] strategy config generation
[ ] run_backtest
[ ] cost direction mapping
[ ] ATR-based sizing
[ ] Fibonacci target
```

---

## Phase 4 — Refactor after notebook runs

Suggested structure:

```text
xauusd_ea/
  __init__.py
  data.py
  indicators.py
  entries.py
  exits.py
  sizing.py
  costs.py
  filters.py
  config_generator.py
  backtest.py
  metrics.py
  walkforward.py
  export.py
  main.py

tests/
  test_indicators.py
  test_config_generator.py
  test_backtest_smoke.py
  test_costs.py
  test_sizing.py
  test_exits.py
```

---

## Phase 5 — Prepare EA export

After strategy selection is trustworthy, export strategy config as JSON suitable for MQL5 EA generation.

Example target JSON:

```json
{
  "symbol": "XAUUSD",
  "timeframe": "M15",
  "contract_size": 100,
  "indicators": ["EMA", "RSI", "ATR"],
  "params": {
    "EMA": {
      "fast": 12,
      "slow": 26
    },
    "RSI": {
      "period": 14
    },
    "ATR": {
      "period": 14
    }
  },
  "entry": {
    "direction": "both",
    "mode": "AND"
  },
  "exit": {
    "sl_type": "atr",
    "tp_type": "rr",
    "atr_multiplier": 2.0,
    "rr_ratio": 2.0
  },
  "sizing": {
    "method": "risk_percent",
    "risk_percent": 1.0,
    "contract_size": 100
  },
  "friction": {
    "spread_points": 1.5,
    "slippage_points": 1.0,
    "commission_per_lot": 7.0,
    "swap_per_lot": -1.0
  },
  "filters": {
    "trend_filter": true,
    "session_filter": true
  }
}
```

---

# Ready-to-Use Prompt for Codex

Use this prompt directly in Codex:

```text
You are working on a Python strategy optimization project for XAUUSD.

Main file:
EA XAUUSD_24072025_Master.ipynb

Goal:
Make the notebook/codebase run end-to-end for a small XAUUSD backtest pipeline first. Do not jump to full optimization or MQL5 conversion yet. The priority is correctness and a clean smoke-testable pipeline.

Project summary:
- Loads MT5-exported XAUUSD OHLCV CSV files for M15, M30, H1, H4.
- Precomputes indicators: EMA, RSI, MACD, Bollinger Bands, ATR, Stochastic, Fibonacci support/resistance.
- Generates strategy configs from combinations of indicators, params, exits, sizing, friction, and filters.
- Supports long/short composite entry logic.
- Supports ATR/structure stop loss, RR/Fibonacci take profit, trailing stop, max holding bars, reversal exit.
- Supports sizing methods: fixed, risk_percent, atr_based.
- Supports trading cost model: slippage, spread, commission, swap.
- Runs backtest, calculates metrics, filters strategies, deduplicates equity curves, runs walk-forward validation, and exports top strategies.

Please fix the code in this priority order:

1. Make the test pipeline run without error.
   - `precompute_indicators` currently requires `combined_params`, but later calls omit it.
   - `evaluate_backtest_configs` currently expects a single DataFrame, but later code passes `data_dict` and `multi_timeframe=True`.
   - Either support both DataFrame and dict inputs or split into single-timeframe and multi-timeframe evaluation functions.
   - Add a very small smoke-test grid that completes quickly.

2. Fix execution direction mapping.
   - `run_backtest` passes `"long"` / `"short"` into `compute_trade_costs`.
   - Cost functions expect `"buy"` / `"sell"`.
   - Correct mapping:
     - long entry = buy
     - long exit = sell
     - short entry = sell
     - short exit = buy

3. Fix ATR-based position sizing.
   - `atr_based` sizing needs current ATR.
   - Inject `current_atr` into sizing config before calling `calculate_position_size`.

4. Fix Fibonacci target logic.
   - `calculate_fib_target` has `if m in fib_levels or True`, which is always true.
   - Use `config["exit"]["fib_levels"]` instead of `config["params"]["Fibonacci"]` for take-profit logic.
   - Make Fibonacci target calculation explicit and testable.

5. Fix indicator parameter usage.
   - MACD optimization params are currently not actually used because only default `macd_histogram` is precomputed.
   - Bollinger Band optimization params are not fully used because `bb_entry` reads default `bb_lower` / `bb_upper` columns.
   - Precompute dynamic columns or simplify the grid so the actual logic matches the optimized params.

6. Make PnL and cost model configurable for XAUUSD.
   - Current PnL uses `price_diff * lot * 100`.
   - Replace hard-coded `100` with `contract_size` from config, default `100`.
   - Confirm spread/slippage units are consistent.

7. Reduce grid explosion.
   - Avoid converting huge `itertools.product` results into list.
   - Use lazy iteration, batching, max_configs, or sampling.
   - Keep full grid optional.

8. Add smoke tests.
   At minimum, add tests for:
   - indicator precompute
   - strategy config generation
   - run_backtest
   - cost direction mapping
   - ATR-based sizing
   - Fibonacci target

9. Refactor only after the notebook runs.
   Suggested modules:
   - data.py
   - indicators.py
   - entries.py
   - exits.py
   - sizing.py
   - costs.py
   - filters.py
   - config_generator.py
   - backtest.py
   - metrics.py
   - walkforward.py
   - export.py
   - main.py

Acceptance criteria:
- A small M15-only test run with a tiny parameter grid completes without exception.
- It returns a non-empty metrics DataFrame or a clear message if no trades.
- No hard-coded local Windows or Colab paths exist inside core functions.
- Backtest engine can run with a single DataFrame input.
- Optional multi-timeframe mode is either implemented cleanly or temporarily disabled with a clear TODO.
- The code has smoke tests for the most important functions.
```

---

# Short Summary

This project is a prototype **XAUUSD strategy optimizer and backtester**.

It already has most components needed for a full pipeline, but it should not be trusted yet until the critical bugs are fixed:

```text
precompute_indicators call mismatch
evaluate_backtest_configs interface mismatch
long/short vs buy/sell cost direction bug
ATR-based sizing missing ATR
Fibonacci target always-true bug
MACD/BB optimized params not actually used
hard-coded contract size
huge strategy grid memory risk
hard-coded local file paths
```

The immediate next step is to make a small single-timeframe M15 test pipeline run end-to-end with a tiny strategy grid.
