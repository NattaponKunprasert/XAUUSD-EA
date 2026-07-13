import pandas as pd
import pytest

from xauusd_ea.metrics import (
    clean_strategies,
    compute_strategy_metrics,
    max_drawdown_fraction,
)


def test_max_drawdown_fraction_tracks_running_peak_and_empty_curve():
    assert max_drawdown_fraction([]) == 0.0
    assert max_drawdown_fraction([1000.0, 1100.0, 990.0, 1080.0]) == pytest.approx(
        0.10
    )


@pytest.mark.parametrize(
    ("equity", "message"),
    [
        ([1000.0, float("nan")], "finite"),
        ([0.0, 1.0], "positive running peak"),
    ],
)
def test_max_drawdown_fraction_rejects_unsafe_equity(equity, message):
    with pytest.raises(ValueError, match=message):
        max_drawdown_fraction(equity)


def test_compute_strategy_metrics_caps_infinite_profit_factor_for_score():
    metrics = compute_strategy_metrics(
        [{"pnl": 1.0, "bars": 2}, {"pnl": 2.0, "bars": 4}],
        equity_curve=[1000.0, 1001.0, 1003.0],
        initial_capital=1000.0,
        bars_per_year=100,
    )

    assert metrics["Profit Factor"] == pytest.approx(999.0)
    assert metrics["# Trades"] == 2
    assert metrics["Win Rate"] == pytest.approx(1.0)
    assert metrics["Avg Trade Duration"] == pytest.approx(3.0)
    assert metrics["Strategy Score"] < 10.0


def test_compute_strategy_metrics_tracks_drawdown_and_loss_streaks():
    metrics = compute_strategy_metrics(
        [
            {"pnl": -1.0, "bars": 1},
            {"pnl": -2.0, "bars": 1},
            {"pnl": 3.0, "bars": 1, "reason": "StoppedEarlyDrawdown"},
        ],
        equity_curve=[1000.0, 998.0, 997.0, 1003.0],
        initial_capital=1000.0,
        bars_per_year=100,
    )

    assert metrics["Max Drawdown"] == pytest.approx(3.0)
    assert metrics["Max Consecutive Losses"] == 2
    assert metrics["Stopped Early"] is True


def test_clean_strategies_applies_trade_drawdown_winrate_and_stopped_filters():
    rows = pd.DataFrame(
        [
            {
                "Strategy ID": "keep",
                "# Trades": 30,
                "Max Drawdown %": 0.10,
                "Win Rate": 0.60,
                "Stopped Early": False,
            },
            {
                "Strategy ID": "too_few",
                "# Trades": 29,
                "Max Drawdown %": 0.10,
                "Win Rate": 0.60,
                "Stopped Early": False,
            },
            {
                "Strategy ID": "stopped",
                "# Trades": 40,
                "Max Drawdown %": 0.10,
                "Win Rate": 0.60,
                "Stopped Early": True,
            },
            {
                "Strategy ID": "winrate_cap",
                "# Trades": 40,
                "Max Drawdown %": 0.10,
                "Win Rate": 1.0,
                "Stopped Early": False,
            },
        ]
    )

    cleaned = clean_strategies(
        rows,
        capital=1000.0,
        min_trades=30,
        max_mdd_pct=0.50,
        win_rate_cap=0.995,
        allow_stopped_early=False,
    )

    assert cleaned["Strategy ID"].tolist() == ["keep"]
