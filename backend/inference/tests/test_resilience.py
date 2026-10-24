import pytest

from inference.errors import InferenceUnavailable
from inference.resilience import CircuitBreaker


def test_breaker_half_opens_after_reset_period() -> None:
    now = [0.0]
    breaker = CircuitBreaker("tts", failure_threshold=2, reset_after_s=10, clock=lambda: now[0])
    breaker.record_failure()
    breaker.record_failure()
    with pytest.raises(InferenceUnavailable):
        breaker.before_call()
    now[0] = 11
    breaker.before_call()  # half-open: one trial call allowed
    breaker.record_failure()  # trial failed: open again immediately
    with pytest.raises(InferenceUnavailable):
        breaker.before_call()
    now[0] = 22
    breaker.before_call()
    breaker.record_success()
    breaker.before_call()  # closed
