"""Small, auditable XAUUSD EA research helpers."""

from .validation import (
    SampleHoldoutSplit,
    UnsafeEvaluationError,
    assert_exact_forward_config_identity,
    research_config_fingerprint,
    research_config_payload,
    split_sample_holdout,
)

__all__ = [
    "SampleHoldoutSplit",
    "UnsafeEvaluationError",
    "assert_exact_forward_config_identity",
    "research_config_fingerprint",
    "research_config_payload",
    "split_sample_holdout",
]
