"""Rate limiting and retry logic shared by all Collectors.

Per architecture Section 14.5/2.4: this lives in CollectorService, never
inside a Collector function. Collectors only know how to fetch from their
one DataSource; CollectorService decides when and how many times to call
them.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from egxpm.shared.exceptions import BusinessDataError

T = TypeVar("T")

TRANSIENT_STATUS_CODES = {429, 503}
_TRANSIENT_MARKERS = ("timeout", "timed out", "429", "503", "connection")


def _is_transient(exc: Exception) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code is not None:
        return status_code in TRANSIENT_STATUS_CODES
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


class CollectorService:
    """Applies a fixed rate-limit delay and the transient/structural retry policy."""

    def __init__(
        self,
        max_retries: int = 3,
        backoff_seconds: tuple[float, ...] = (2.0, 4.0, 8.0),
    ):
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def collect(self, fetch_fn: Callable[[], T], *, min_delay_seconds: float = 0.0) -> T:
        """Runs fetch_fn() under the rate-limit + retry policy.

        Raises:
            BusinessDataError: fetch_fn's own BusinessDataError subclasses
                propagate unchanged (already structural/explicit); any other
                exception is classified as transient (retried) or structural
                (raised immediately, wrapped in BusinessDataError).
            ValueError, AssertionError: never caught here — these are
                Programmer Errors per the Error Handling Rules and must
                surface loudly, not be retried or reclassified as a
                business/data failure. Without this exclusion, a genuine
                bug inside a Collector (a bad-type ValueError, a violated
                assertion) would be silently retried 3x and swallowed into
                a per-company-isolated BusinessDataError like any ordinary
                scraping failure, hiding the bug.
        """
        if min_delay_seconds > 0:
            time.sleep(min_delay_seconds)

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return fetch_fn()
            except BusinessDataError:
                raise
            except (ValueError, AssertionError):
                raise
            except Exception as exc:
                if not _is_transient(exc):
                    raise BusinessDataError(f"structural collection failure: {exc}") from exc
                last_error = exc
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_seconds[attempt])

        raise BusinessDataError(
            f"transient collection failure after {self.max_retries} attempts: {last_error}"
        ) from last_error
