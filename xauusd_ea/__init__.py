"""Small, auditable XAUUSD EA research helpers."""

from .validation import (
    SampleHoldoutSplit,
    UnsafeEvaluationError,
    WalkForwardWindow,
    assert_exact_forward_config_identity,
    plan_walk_forward_windows,
    research_config_fingerprint,
    research_config_payload,
    split_sample_holdout,
)

__all__ = [
    "SampleHoldoutSplit",
    "UnsafeEvaluationError",
    "WalkForwardWindow",
    "assert_exact_forward_config_identity",
    "plan_walk_forward_windows",
    "research_config_fingerprint",
    "research_config_payload",
    "split_sample_holdout",
]
