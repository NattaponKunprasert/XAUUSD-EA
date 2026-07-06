"""Small, auditable XAUUSD EA research helpers."""

from .baseline import (
    BrokerProfile,
    assert_runtime_broker_spec_matches_profile,
    load_broker_profile,
)
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
