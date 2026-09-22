"""Which sources a request ends up querying."""

import pytest
from sqlalchemy.orm import Session

from bluecore_api.federated.http import new_client
from bluecore_api.federated.registry import (
    SourceContext,
    UnknownSourceError,
    configured_source_ids,
    resolve_sources,
)


@pytest.fixture
def ctx(db_session: Session) -> SourceContext:
    """A real context. These tests only look at which sources come back, but
    building them for real is what proves the factories actually wire up."""
    return SourceContext(db=db_session, http=new_client())


def test_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("FEDERATED_SEARCH_SOURCES", raising=False)
    assert configured_source_ids() == ["bluecore", "loc"]


def test_environment_sets_the_order(monkeypatch, ctx):
    """Order is the group order in the response, so operations can demote a
    source without a deploy."""
    monkeypatch.setenv("FEDERATED_SEARCH_SOURCES", "loc,bluecore")
    assert [s.id for s in resolve_sources(ctx)] == ["loc", "bluecore"]


def test_a_source_can_be_turned_off(monkeypatch, ctx):
    monkeypatch.setenv("FEDERATED_SEARCH_SOURCES", "bluecore")
    assert [s.id for s in resolve_sources(ctx)] == ["bluecore"]


def test_unknown_id_in_the_environment_is_skipped_not_fatal(monkeypatch, caplog):
    """A typo in a deployment variable should not take the API down."""
    monkeypatch.setenv("FEDERATED_SEARCH_SOURCES", "bluecore,typo")
    assert configured_source_ids() == ["bluecore"]
    assert "typo" in caplog.text


def test_a_disabled_source_cannot_be_switched_on_by_the_client(monkeypatch, ctx):
    """The environment is the ceiling; `sources=` can only narrow it."""
    monkeypatch.setenv("FEDERATED_SEARCH_SOURCES", "bluecore")
    assert [s.id for s in resolve_sources(ctx, "bluecore,loc")] == ["bluecore"]


def test_unknown_id_from_the_client_is_an_error(ctx):
    with pytest.raises(UnknownSourceError, match="Unknown source"):
        resolve_sources(ctx, "nope")
