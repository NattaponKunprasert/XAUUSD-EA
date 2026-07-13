"""Deterministic strategy metrics and cleaning helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


DEFAULT_METRICS = {
    "Net Profit": 0.0,
    "CAGR": 0.0,
    "Max Drawdown": 0.0,
    "Max Drawdown %": 0.0,
    "Volatility": 0.0,
    "Sharpe Ratio": 0.0,
    "Sortino Ratio": 0.0,
    "Win Rate": 0.0,
    "Profit Factor": 0.0,
    "# Trades": 0,
    "Avg Trade Duration": 0.0,
    "Expectancy": 0.0,
    "Recovery Factor": 0.0,
    "Max Consecutive Losses": 0,
    "Stopped Early": False,
    "Strategy Score": 0.0,
}


def max_drawdown_fraction(equity_curve) -> float:
    """Return peak-to-trough drawdown as a fraction of the running peak.

    The active engine uses this during a backtest to enforce its configured
    early-stop threshold. Non-finite equity or a non-positive running peak is
    rejected because either state makes percentage drawdown unsafe to infer.
    """
    equity = pd.Series(equity_curve, dtype=float)
    if equity.empty:
        return 0.0
    if not np.isfinite(equity.to_numpy()).all():
        raise ValueError("equity_curve must contain only finite values")

    peak = equity.cummax()
    if (peak <= 0.0).any():
        raise ValueError("equity_curve must have a positive running peak")
    return float(((peak - equity) / peak).max())


def compute_strategy_metrics(
    trades: list[dict[str, Any]],
    equity_curve=None,
    *,
    initial_capital: float,
    bars_per_year: int,
) -> dict[str, float | int | bool]:
    """Compute active-engine metrics without notebook-local state."""
    eq = pd.Series(
        equity_curve if equity_curve is not None and len(equity_curve) else [initial_capital],
        dtype=float,
    )
    if eq.empty:
        eq = pd.Series([initial_capital], dtype=float)
    final_equity = float(eq.iloc[-1])
    net_profit = final_equity - float(initial_capital)

    n_bars = max(len(eq), 1)
    years = n_bars / float(bars_per_year) if bars_per_year else 0.0
    cagr = (
        (final_equity / initial_capital) ** (1 / years) - 1
        if years > 0 and final_equity > 0
        else 0.0
    )

    peak = eq.cummax()
    drawdown_abs = float((peak - eq).max())
    drawdown_pct = max_drawdown_fraction(eq)

    returns = eq.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if len(returns) > 1 and returns.std() > 0:
        volatility = float(returns.std() * np.sqrt(bars_per_year))
        sharpe = float(returns.mean() / returns.std() * np.sqrt(bars_per_year))
        downside = returns[returns < 0]
        sortino = (
            float(returns.mean() / downside.std() * np.sqrt(bars_per_year))
            if len(downside) > 1 and downside.std() > 0
            else 0.0
        )
    else:
        volatility, sharpe, sortino = 0.0, 0.0, 0.0

    if not trades:
        return dict(DEFAULT_METRICS)

    trades_df = pd.DataFrame(trades)
    stopped_early = bool(
        "reason" in trades_df.columns
        and trades_df["reason"]
        .astype(str)
        .str.contains("StoppedEarly", case=False, na=False)
        .any()
    )
    wins = trades_df[trades_df["pnl"] > 0]
    losses = trades_df[trades_df["pnl"] < 0]
    win_rate = float(len(wins) / len(trades_df)) if len(trades_df) else 0.0
    gross_profit = float(wins["pnl"].sum()) if len(wins) else 0.0
    gross_loss = abs(float(losses["pnl"].sum())) if len(losses) else 0.0
    profit_factor_raw = (
        np.inf
        if gross_loss == 0 and gross_profit > 0
        else (gross_profit / gross_loss if gross_loss > 0 else 0.0)
    )
    profit_factor_for_score = min(
        float(profit_factor_raw if np.isfinite(profit_factor_raw) else 5.0),
        5.0,
    )
    expectancy = float(trades_df["pnl"].mean())
    average_duration = (
        float(trades_df["bars"].mean()) if "bars" in trades_df.columns else 0.0
    )

    loss_flags = (trades_df["pnl"] < 0).astype(int)
    groups = (loss_flags != loss_flags.shift()).cumsum()
    max_consecutive_losses = (
        int(loss_flags.groupby(groups).sum().max()) if len(loss_flags) else 0
    )
    recovery = float(net_profit / drawdown_abs) if drawdown_abs > 0 else 0.0

    score = (
        min(max(sharpe, -5), 5) * 0.30
        + min(max(sortino, -5), 5) * 0.15
        + min(profit_factor_for_score, 5) * 0.20
        + win_rate * 0.10
        + min(max(cagr, -1), 3) * 0.15
        - min(drawdown_pct, 1.0) * 0.10
    )

    return {
        "Net Profit": float(net_profit),
        "CAGR": float(cagr),
        "Max Drawdown": float(drawdown_abs),
        "Max Drawdown %": float(drawdown_pct),
        "Volatility": float(volatility),
        "Sharpe Ratio": float(sharpe),
        "Sortino Ratio": float(sortino),
        "Win Rate": float(win_rate),
        "Profit Factor": float(
            profit_factor_raw if np.isfinite(profit_factor_raw) else 999.0
        ),
        "# Trades": int(len(trades_df)),
        "Avg Trade Duration": average_duration,
        "Expectancy": expectancy,
        "Recovery Factor": recovery,
        "Max Consecutive Losses": max_consecutive_losses,
        "Stopped Early": bool(stopped_early),
        "Strategy Score": float(score),
    }


def clean_strategies(
    df: pd.DataFrame,
    *,
    capital: float,
    min_trades: int = 30,
    max_mdd_pct: float = 0.50,
    win_rate_cap: float = 0.995,
    allow_stopped_early: bool = True,
) -> pd.DataFrame:
    """Apply active-engine quality filters to evaluated strategy rows."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out = out[out["# Trades"] >= int(min_trades)]
    if "Max Drawdown %" in out.columns:
        out = out[out["Max Drawdown %"] <= float(max_mdd_pct)]
    else:
        out = out[out["Max Drawdown"] <= float(max_mdd_pct) * float(capital)]
    out = out[out["Win Rate"] <= float(win_rate_cap)]
    if not allow_stopped_early and "Stopped Early" in out.columns:
        out = out[out["Stopped Early"] == False]
    return out.reset_index(drop=True)
