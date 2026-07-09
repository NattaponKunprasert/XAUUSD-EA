"""Deterministic entry-filter composition helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd


EntryFilter = Callable[[pd.DataFrame, int, dict[str, Any]], bool]


def passes_entry_filters(
    df: pd.DataFrame,
    index: int,
    filters: Mapping[str, Any] | None,
    *,
    filter_params: Mapping[str, Any] | None = None,
    registry: Mapping[str, EntryFilter] | None = None,
    verbose: bool = False,
    return_dict: bool = False,
) -> bool | dict[str, bool]:
    """Apply enabled entry filters at one already-selected signal-bar index.

    ``index`` is supplied by the caller, so next-bar engines can explicitly pass
    the fully closed signal bar instead of the executable entry bar.
    """
    active_filters = dict(filters or {})
    active_params = dict(filter_params or {})
    active_registry = dict(registry or {})
    results: dict[str, bool] = {}
    all_pass = True

    for raw_name, is_enabled in active_filters.items():
        if not is_enabled:
            continue

        base_name = str(raw_name).replace("use_", "", 1)
        func = active_registry.get(base_name)
        if func is None:
            if verbose:
                print(f"[Filter] {base_name}: function not found.")
            results[base_name] = False
            all_pass = False
            continue

        passed = bool(func(df, index, dict(active_params.get(base_name, {}))))
        results[base_name] = passed
        if verbose:
            print(f"[Filter] {base_name}: {passed}")
        if not passed:
            all_pass = False

    return results if return_dict else all_pass
