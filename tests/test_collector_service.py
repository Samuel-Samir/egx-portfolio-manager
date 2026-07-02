import pytest

from egxpm.collectors.collector_service import CollectorService
from egxpm.shared.exceptions import BusinessDataError, InsufficientDataError


def test_returns_fetch_fn_result_on_success():
    service = CollectorService()
    assert service.collect(lambda: "ok") == "ok"


def test_business_data_error_propagates_unchanged_no_retry():
    calls = []

    def fetch():
        calls.append(1)
        raise InsufficientDataError("no data")

    service = CollectorService(max_retries=3, backoff_seconds=(0, 0, 0))
    with pytest.raises(InsufficientDataError):
        service.collect(fetch)
    assert len(calls) == 1  # BusinessDataError is already explicit — never retried


def test_transient_error_is_retried_then_succeeds():
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("HTTP 429 Too Many Requests")
        return "recovered"

    service = CollectorService(max_retries=3, backoff_seconds=(0, 0, 0))
    assert service.collect(fetch) == "recovered"
    assert len(calls) == 3


def test_transient_error_exhausts_retries_and_raises_business_data_error():
    calls = []

    def fetch():
        calls.append(1)
        raise RuntimeError("connection timeout")

    service = CollectorService(max_retries=3, backoff_seconds=(0, 0, 0))
    with pytest.raises(BusinessDataError):
        service.collect(fetch)
    assert len(calls) == 3


def test_structural_error_raises_immediately_without_retry():
    calls = []

    def fetch():
        calls.append(1)
        raise RuntimeError("unexpected page layout")

    service = CollectorService(max_retries=3, backoff_seconds=(0, 0, 0))
    with pytest.raises(BusinessDataError):
        service.collect(fetch)
    assert len(calls) == 1  # not a transient marker — no retry


def test_value_error_surfaces_loudly_not_wrapped_or_retried():
    calls = []

    def fetch():
        calls.append(1)
        raise ValueError("bad input — a real bug, not a data failure")

    service = CollectorService(max_retries=3, backoff_seconds=(0, 0, 0))
    with pytest.raises(ValueError):
        service.collect(fetch)
    assert len(calls) == 1  # programmer error — never retried, never wrapped


def test_assertion_error_surfaces_loudly_not_wrapped_or_retried():
    def fetch():
        raise AssertionError("invariant violated")

    service = CollectorService(max_retries=3, backoff_seconds=(0, 0, 0))
    with pytest.raises(AssertionError):
        service.collect(fetch)


def test_min_delay_seconds_sleeps_before_first_attempt(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    service = CollectorService()
    service.collect(lambda: "ok", min_delay_seconds=1.5)
    assert slept == [1.5]
