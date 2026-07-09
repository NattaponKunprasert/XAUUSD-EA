import pandas as pd

from xauusd_ea.entries import (
    compose_entry_signals,
    normalized_combo_key,
    resolve_entry_pair,
)


def _df() -> pd.DataFrame:
    return pd.DataFrame(index=pd.date_range("2025-01-01", periods=4, freq="15min"))


def _caller(fn, indicator, df, params):
    return fn(df, params.get(indicator, {}))


def _signal(values):
    def _fn(df, params):
        return pd.Series(values, index=df.index)

    return _fn


def test_compose_entry_signals_supports_and_or_vote_modes():
    df = _df()
    pairs = [
        (_signal([True, True, False, False]), "A"),
        (_signal([True, False, True, False]), "B"),
        (_signal([False, True, True, False]), "C"),
    ]

    and_signal = compose_entry_signals(pairs, signal_caller=_caller, mode="AND")
    or_signal = compose_entry_signals(pairs, signal_caller=_caller, mode="OR")
    vote_signal = compose_entry_signals(pairs, signal_caller=_caller, mode="VOTE")
    two_vote_signal = compose_entry_signals(
        pairs,
        signal_caller=_caller,
        mode="VOTE",
        min_confirmations=2,
    )

    assert and_signal(df).tolist() == [False, False, False, False]
    assert or_signal(df).tolist() == [True, True, True, False]
    assert vote_signal(df).tolist() == [True, True, True, False]
    assert two_vote_signal(df).tolist() == [True, True, True, False]


def test_compose_entry_signals_returns_false_series_for_empty_combo():
    df = _df()
    signal = compose_entry_signals([], signal_caller=_caller, mode="OR")

    assert signal(df).tolist() == [False, False, False, False]
    assert signal(df).index.equals(df.index)


def test_resolve_entry_pair_builds_directional_composites_and_names_strategy():
    df = _df()
    entry_functions = {
        "EMA": _signal([True, True, False, False]),
        "RSI": _signal([True, False, True, False]),
    }
    short_entry_functions = {
        "EMA": _signal([False, True, True, False]),
        "RSI": _signal([True, True, False, False]),
    }

    long_fn, short_fn, name = resolve_entry_pair(
        entry_functions,
        short_entry_functions,
        ("RSI", "EMA"),
        signal_caller=_caller,
        entry_logic={"mode": "OR"},
    )

    assert name == "OR_EMA_RSI"
    assert long_fn(df).tolist() == [True, True, True, False]
    assert short_fn(df).tolist() == [True, True, True, False]
    assert normalized_combo_key(("RSI", "EMA")) == "EMA_RSI"


def test_resolve_entry_pair_respects_custom_combo_and_skip_indicators():
    custom_long = _signal([True, False, False, False])
    custom_short = _signal([False, True, False, False])
    entry_functions = {
        "EMA_RSI": {"long": custom_long, "short": custom_short},
        "EMA": _signal([False, False, False, False]),
        "RSI": _signal([False, False, False, False]),
    }
    short_entry_functions = {
        "EMA": _signal([False, False, False, False]),
        "RSI": _signal([False, False, False, False]),
    }

    long_fn, short_fn, name = resolve_entry_pair(
        entry_functions,
        short_entry_functions,
        ("RSI", "EMA"),
        signal_caller=_caller,
    )
    skipped = resolve_entry_pair(
        {"EMA": _signal([True] * 4)},
        {"EMA": _signal([True] * 4)},
        ("EMA",),
        signal_caller=_caller,
        skip_indicators=frozenset({"EMA"}),
    )

    assert (long_fn, short_fn, name) == (custom_long, custom_short, "EMA_RSI")
    assert skipped == (None, None, None)
