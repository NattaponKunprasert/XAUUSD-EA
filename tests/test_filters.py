import pandas as pd

from xauusd_ea.filters import passes_entry_filters


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "close": [100.0, 101.0, 99.0],
            "volume": [10.0, 20.0, 5.0],
        },
        index=pd.date_range("2025-01-01", periods=3, freq="15min"),
    )


def test_passes_entry_filters_uses_supplied_signal_index_and_params():
    seen: dict[str, object] = {}

    def close_above(frame, index, params):
        seen["timestamp"] = frame.index[index]
        seen["threshold"] = params["threshold"]
        return frame.iloc[index]["close"] > params["threshold"]

    result = passes_entry_filters(
        _df(),
        1,
        {"use_close_above": True},
        filter_params={"close_above": {"threshold": 100.5}},
        registry={"close_above": close_above},
    )

    assert result is True
    assert seen == {
        "timestamp": pd.Timestamp("2025-01-01 00:15"),
        "threshold": 100.5,
    }


def test_passes_entry_filters_returns_individual_results_and_ignores_disabled():
    def always_false(frame, index, params):
        return False

    results = passes_entry_filters(
        _df(),
        0,
        {
            "use_disabled": False,
            "use_always_false": True,
        },
        registry={"always_false": always_false, "disabled": always_false},
        return_dict=True,
    )

    assert results == {"always_false": False}


def test_passes_entry_filters_fails_closed_for_unknown_enabled_filter():
    assert (
        passes_entry_filters(
            _df(),
            0,
            {"use_missing_filter": True},
            registry={},
        )
        is False
    )


def test_passes_entry_filters_accepts_empty_filter_set():
    assert passes_entry_filters(_df(), 0, None, registry={}) is True
