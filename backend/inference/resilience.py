"""A minimal circuit breaker so an unavailable native service fails fast instead of making
every request wait for a connection timeout."""

import threading
import time
from collections.abc import Callable

from .errors import InferenceUnavailable


class CircuitBreaker:
    def __init__(
        self,
        service: str,
        *,
        failure_threshold: int = 3,
        reset_after_s: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.service = service
        self.failure_threshold = failure_threshold
        self.reset_after_s = reset_after_s
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def before_call(self) -> None:
        with self._lock:
            if self._opened_at is None:
                return
            if self._clock() - self._opened_at < self.reset_after_s:
                raise InferenceUnavailable(
                    self.service, f"{self.service} is unavailable (retrying shortly)"
                )
            # Half-open: let one call through; its outcome closes or re-opens the circuit.
            self._opened_at = None
            self._failures = self.failure_threshold - 1

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = self._clock()
