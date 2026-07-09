"""Entry signal composition helpers for the active research engine."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pandas as pd


SignalCaller = Callable[[Any, str, pd.DataFrame, dict[str, Any]], pd.Series]


def compose_entry_signals(
    pairs: Sequence[tuple[Any, str]],
    *,
    signal_caller: SignalCaller,
    mode: str = "AND",
    min_confirmations: int | None = None,
) -> Callable[[pd.DataFrame, dict[str, Any] | None], pd.Series]:
    """Return a deterministic composite entry signal function.

    The caller is responsible for preparing any candidate-specific indicator
    columns. This helper only combines already-causal boolean signal series.
    """
    frozen_pairs = tuple(pairs)
    normalized_mode = str(mode or "AND").upper()

    def _run(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.Series:
        signals = [
            pd.Series(
                signal_caller(fn, ind_key, df, params or {}),
                index=df.index,
            )
            .fillna(False)
            .astype(bool)
            for fn, ind_key in frozen_pairs
        ]
        if not signals:
            return pd.Series(False, index=df.index)

        matrix = pd.concat(signals, axis=1).fillna(False).astype(bool)
        if normalized_mode == "OR":
            return matrix.any(axis=1)
        if normalized_mode == "VOTE":
            required = min_confirmations
            if required is None:
                required = int(math.ceil(len(signals) / 2.0))
            return matrix.sum(axis=1) >= int(required)
        return matrix.all(axis=1)

    return _run


def normalized_combo_key(combo: Sequence[str]) -> str:
    """Return the notebook-compatible normalized key for an indicator combo."""
    return "_".join(sorted(map(str, combo)))


def resolve_entry_pair(
    entry_functions: Mapping[str, Any],
    short_entry_functions: Mapping[str, Any],
    combo: Sequence[str],
    *,
    signal_caller: SignalCaller,
    entry_logic: Mapping[str, Any] | None = None,
    skip_indicators: set[str] | frozenset[str] = frozenset(),
    default_mode: str = "AND",
    default_min_confirmations: int | None = None,
) -> tuple[Callable[..., pd.Series] | None, Callable[..., pd.Series] | None, str | None]:
    """Resolve long/short entry functions for one frozen indicator combo."""
    active_entry_logic = dict(entry_logic or {})
    mode = active_entry_logic.get("mode", default_mode)
    min_confirmations = active_entry_logic.get(
        "min_confirmations", default_min_confirmations
    )

    if isinstance(entry_functions, Mapping):
        key_norm = normalized_combo_key(combo)
        for key, value in entry_functions.items():
            if isinstance(value, Mapping) and "long" in value and "short" in value:
                candidate = str(key).replace("|", "_").upper().split("_")
                if set(candidate) == set(key_norm.upper().split("_")):
                    return value["long"], value["short"], str(key)

    long_pairs: list[tuple[Any, str]] = []
    short_pairs: list[tuple[Any, str]] = []
    names: list[str] = []
    for indicator in combo:
        if indicator in skip_indicators:
            return None, None, None
        if indicator not in entry_functions or indicator not in short_entry_functions:
            return None, None, None
        long_pairs.append((entry_functions[indicator], indicator))
        short_pairs.append((short_entry_functions[indicator], indicator))
        names.append(indicator)

    strategy_name = f"{mode}_" + "_".join(sorted(names))
    return (
        compose_entry_signals(
            long_pairs,
            signal_caller=signal_caller,
            mode=mode,
            min_confirmations=min_confirmations,
        ),
        compose_entry_signals(
            short_pairs,
            signal_caller=signal_caller,
            mode=mode,
            min_confirmations=min_confirmations,
        ),
        strategy_name,
    )
