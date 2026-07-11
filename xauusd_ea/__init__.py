"""Small, auditable XAUUSD EA research helpers."""

from .accounting import gross_pnl, mark_to_market_equity
from .baseline import (
    BrokerProfile,
    assert_runtime_broker_spec_matches_profile,
    load_broker_profile,
)
from .exits import fibonacci_extension_target
from .execution import apply_execution_price, commission_per_side
from .filters import passes_entry_filters
from .indicators import bollinger_bands, macd, stochastic_oscillator
from .sizing import calculate_position_size
from .validation import (
    SampleHoldoutSplit,
    UnsafeEvaluationError,
    assert_expected_research_config_fingerprint,
    WalkForwardWindow,
    assert_exact_forward_config_identity,
    plan_walk_forward_windows,
    research_config_fingerprint,
    research_config_payload,
    split_sample_holdout,
)

__all__ = [
    "BrokerProfile",
    "gross_pnl",
    "mark_to_market_equity",
    "bollinger_bands",
    "apply_execution_price",
    "commission_per_side",
    "calculate_position_size",
    "fibonacci_extension_target",
    "passes_entry_filters",
    "macd",
    "stochastic_oscillator",
    "SampleHoldoutSplit",
    "UnsafeEvaluationError",
    "assert_expected_research_config_fingerprint",
    "assert_runtime_broker_spec_matches_profile",
    "WalkForwardWindow",
    "assert_exact_forward_config_identity",
    "load_broker_profile",
    "plan_walk_forward_windows",
    "research_config_fingerprint",
    "research_config_payload",
    "split_sample_holdout",
]
