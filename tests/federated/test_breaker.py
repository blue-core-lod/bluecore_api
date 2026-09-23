"""Not asking a source that has stopped answering."""

import pytest

from bluecore_api.federated import breaker


@pytest.fixture(autouse=True)
def clean():
    breaker.reset()
    yield
    breaker.reset()


def test_a_healthy_source_is_never_skipped():
    for _ in range(10):
        breaker.record_success("loc")
    assert breaker.is_open("loc") is False


def test_an_unknown_source_is_not_skipped():
    assert breaker.is_open("never-heard-of-it") is False


def test_it_takes_repeated_failures_to_trip(monkeypatch):
    """One blip should not take a source out; a real outage should."""
    monkeypatch.setenv("FEDERATED_SEARCH_BREAKER_THRESHOLD", "3")

    breaker.record_failure("loc")
    breaker.record_failure("loc")
    assert breaker.is_open("loc") is False

    breaker.record_failure("loc")
    assert breaker.is_open("loc") is True


def test_a_success_clears_the_count(monkeypatch):
    monkeypatch.setenv("FEDERATED_SEARCH_BREAKER_THRESHOLD", "3")

    breaker.record_failure("loc")
    breaker.record_failure("loc")
    breaker.record_success("loc")
    breaker.record_failure("loc")

    assert breaker.is_open("loc") is False


def test_one_request_is_let_through_after_the_cooldown(monkeypatch):
    monkeypatch.setenv("FEDERATED_SEARCH_BREAKER_THRESHOLD", "1")
    monkeypatch.setenv("FEDERATED_SEARCH_BREAKER_COOLDOWN", "0")

    breaker.record_failure("loc")

    # Cooldown of zero means the very next check probes again rather than
    # leaving the source skipped forever.
    assert breaker.is_open("loc") is False


def test_it_stays_shut_for_the_cooldown(monkeypatch):
    monkeypatch.setenv("FEDERATED_SEARCH_BREAKER_THRESHOLD", "1")
    monkeypatch.setenv("FEDERATED_SEARCH_BREAKER_COOLDOWN", "300")

    breaker.record_failure("loc")

    assert breaker.is_open("loc") is True
    assert breaker.is_open("loc") is True


def test_sources_trip_independently(monkeypatch):
    monkeypatch.setenv("FEDERATED_SEARCH_BREAKER_THRESHOLD", "1")
    monkeypatch.setenv("FEDERATED_SEARCH_BREAKER_COOLDOWN", "300")

    breaker.record_failure("loc")

    assert breaker.is_open("loc") is True
    assert breaker.is_open("bluecore") is False
