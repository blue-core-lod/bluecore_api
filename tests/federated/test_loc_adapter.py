"""The id.loc.gov adapter: URL construction and hit mapping.

Pure functions, no app and no database. The payloads are real responses
recorded from id.loc.gov (tests/loc-suggest2-*.json); hand-written ones would
have encoded the start=/offset= and rank-is-relevance mistakes and these tests
would have passed anyway.
"""

import json
import pathlib
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from bluecore_api.constants import SearchScope, SearchType
from bluecore_api.federated.base import FederatedQuery, FederatedSearchError
from bluecore_api.federated.sources.loc import (
    LibraryOfCongressSource,
    summary_jsonld,
    title_from,
)


def payload(name: str) -> dict:
    with pathlib.Path(f"tests/loc-suggest2-{name}.json").open() as fo:
        return json.load(fo)


def query(
    q: str = "melville moby",
    type: SearchType = SearchType.WORKS,
    scope: SearchScope = SearchScope.ALL,
    limit: int = 20,
    offset: int = 0,
) -> FederatedQuery:
    return FederatedQuery(q=q, type=type, scope=scope, limit=limit, offset=offset)


def nodes(data: dict[str, object], key: str) -> list[Any]:
    """Pull a list-valued key out of a synthesized summary.

    summary_jsonld is typed dict[str, object] because JSON-LD values genuinely
    vary; this asserts the shape the test is about to index into.
    """
    value = data[key]
    assert isinstance(value, list), f"{key} should be a list, got {type(value)}"
    return value


@pytest.fixture
def source(httpx_mock) -> LibraryOfCongressSource:
    return LibraryOfCongressSource(httpx.AsyncClient())


# --- URL and parameters -------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("type_", "directory"),
    [
        (SearchType.WORKS, "works"),
        (SearchType.INSTANCES, "instances"),
        (SearchType.HUBS, "hubs"),
    ],
)
async def test_each_type_hits_its_own_directory(httpx_mock, source, type_, directory):
    httpx_mock.add_response(json=payload("empty"))

    await source.search(query(type=type_))

    request = httpx_mock.get_requests()[0]
    assert request.url.path == f"/resources/{directory}/suggest2/"


@pytest.mark.asyncio
async def test_paging_uses_offset_not_start(httpx_mock, source):
    """suggest2 accepts start= and silently ignores it, returning page one
    forever. Verified live: start=21 echoes "start": 1, offset=20 echoes 20."""
    httpx_mock.add_response(json=payload("empty"))

    await source.search(query(offset=20))

    params = httpx_mock.get_requests()[0].url.params
    assert params["offset"] == "20"
    assert "start" not in params


@pytest.mark.asyncio
async def test_keyword_searchtype_is_requested(httpx_mock, source):
    """The default, left-anchored, alpha-sorts -- useless for finding a record."""
    httpx_mock.add_response(json=payload("empty"))

    await source.search(query())

    assert httpx_mock.get_requests()[0].url.params["searchtype"] == "keyword"


@pytest.mark.asyncio
async def test_count_is_clamped(httpx_mock, source):
    httpx_mock.add_response(json=payload("empty"))

    await source.search(query(limit=100))

    assert httpx_mock.get_requests()[0].url.params["count"] == "25"


@pytest.mark.asyncio
async def test_query_is_not_rewritten_as_tsquery(httpx_mock, source):
    """search.py's format_query emits Postgres syntax (& | <-> :*) that LC
    would receive literally, and suggest2 truncates the last token itself."""
    httpx_mock.add_response(json=payload("empty"))

    await source.search(query(q='moby "white whale"'))

    assert httpx_mock.get_requests()[0].url.params["q"] == 'moby "white whale"'


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["", "   "])
async def test_blank_query_makes_no_request(httpx_mock, source, blank):
    """An empty q against suggest2 is a wildcard scan of 23.8 million records."""
    results = await source.search(query(q=blank))

    assert results.results == []
    assert httpx_mock.get_requests() == []


@pytest.mark.asyncio
async def test_deep_paging_is_refused_without_a_request(httpx_mock, source):
    results = await source.search(query(offset=5000))

    assert results.truncated is True
    assert httpx_mock.get_requests() == []


@pytest.mark.asyncio
async def test_type_all_covers_works_only_by_default(httpx_mock, source):
    """type=all is the editor's default; three directory requests per search
    would triple our traffic for marginal recall."""
    httpx_mock.add_response(json=payload("works"))

    results = await source.search(query(type=SearchType.ALL))

    assert len(httpx_mock.get_requests()) == 1
    assert httpx_mock.get_requests()[0].url.path == "/resources/works/suggest2/"
    assert results.note == "Library of Congress results cover Works."


@pytest.mark.asyncio
async def test_type_all_can_be_widened(httpx_mock, monkeypatch, source):
    monkeypatch.setenv("LOC_SEARCH_DIRECTORIES", "works,instances,hubs")
    for name in ("works", "instances", "hubs"):
        httpx_mock.add_response(json=payload(name))

    results = await source.search(query(type=SearchType.ALL))

    assert len(httpx_mock.get_requests()) == 3
    assert results.note is None
    # Totals are summed across the directories that were asked.
    assert results.total == 190 + 204 + 30


# --- Mapping ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_maps_a_real_hit(httpx_mock, source):
    httpx_mock.add_response(json=payload("works"))

    results = await source.search(query())
    first = results.results[0]

    assert first.source == "loc"
    assert first.source_label == "Library of Congress"
    # Left as http://, the form LC returns and the form stored in derivedFrom.
    assert first.uri == "http://id.loc.gov/resources/works/13337906"
    assert first.type == "works"
    assert first.updated_at == datetime(2023, 2, 1, tzinfo=UTC)
    # LC exposes no creation date and a guess would render as a Created column.
    assert first.created_at is None
    assert first.related == {
        "instance": "http://id.loc.gov/resources/instances/13337906"
    }
    assert first.local_uri is None


@pytest.mark.asyncio
async def test_total_is_the_sources_own_estimate(httpx_mock, source):
    httpx_mock.add_response(json=payload("works"))

    results = await source.search(query())

    assert results.total == 190
    assert results.total_is_exact is False


@pytest.mark.asyncio
async def test_rank_is_kept_as_a_number_but_not_as_relevance(httpx_mock, source):
    """Six different works for this query all score 23803: it is a static
    per-access-point weight, only meaningful for ordering within this source."""
    httpx_mock.add_response(json=payload("works"))

    results = await source.search(query())

    assert results.results[0].rank == 23803.0


def test_title_strips_the_contributor_prefix():
    hit = payload("works")["hits"][0]
    assert hit["aLabel"] == "Melville, Herman, 1819-1891. Moby-Dick, or, The whale"

    assert title_from(hit) == "Moby-Dick, or, The whale"


def test_title_falls_back_to_the_shorter_variant_label():
    hit = {
        "aLabel": "Some very long access point heading",
        "vLabel": "Short title",
        "more": {"contributors": []},
    }
    assert title_from(hit) == "Short title"


def test_title_falls_back_to_the_access_point():
    hit = {"aLabel": "Just a title", "vLabel": "", "more": {}}
    assert title_from(hit) == "Just a title"


def test_title_keeps_the_access_point_when_the_prefix_does_not_match():
    hit = {
        "aLabel": "Moby-Dick, or, The whale",
        "vLabel": "",
        "more": {"contributors": ["Melville, Herman, 1819-1891"]},
    }
    assert title_from(hit) == "Moby-Dick, or, The whale"


def test_summary_is_shaped_for_the_editors_hit_mapper():
    """sinopia_editor's hitsToResult reads data["@type"] (bare class names it
    namespaces itself), data.title[].mainTitle and
    data.contribution[].agent.label."""
    data = summary_jsonld(payload("works")["hits"][0])

    assert data["@type"] == ["Work", "Text", "Monograph"]
    assert nodes(data, "title")[0] == {
        "@type": "Title",
        "mainTitle": "Moby-Dick, or, The whale",
    }
    contributions = nodes(data, "contribution")
    assert contributions[0] == {
        "@type": "PrimaryContribution",
        "agent": {"@type": "Agent", "label": "Melville, Herman, 1819-1891"},
    }
    assert contributions[1]["@type"] == "Contribution"
    # The untouched access point survives for the HTML view's title fallback.
    assert data["bflc:aap"] == "Melville, Herman, 1819-1891. Moby-Dick, or, The whale"
    assert data["identifiedBy"] == [{"@type": "Lccn", "value": "2003272426"}]
    # The summary says it is derived and that it came from the search API.
    assert nodes(data, "adminMetadata")[0]["derivedFrom"] == {
        "@id": "http://id.loc.gov/resources/works/13337906"
    }


def test_summary_survives_a_thin_more_block():
    """The instances directory carries no contributors, genres or subjects."""
    hit = payload("instances")["hits"][0]

    data = summary_jsonld(hit)

    assert data["@id"] == hit["uri"]
    assert "contribution" not in data
    assert nodes(data, "title")[0]["mainTitle"]


# --- Failures -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_http_error_becomes_a_readable_message(httpx_mock, source):
    httpx_mock.add_response(status_code=503)

    with pytest.raises(FederatedSearchError, match="returned HTTP 503"):
        await source.search(query())


@pytest.mark.asyncio
async def test_unreachable_host_becomes_a_readable_message(httpx_mock, source):
    httpx_mock.add_exception(httpx.ConnectError("nope"))

    with pytest.raises(FederatedSearchError, match="Could not reach"):
        await source.search(query())


@pytest.mark.asyncio
async def test_unreadable_body_becomes_a_readable_message(httpx_mock, source):
    httpx_mock.add_response(content=b"<html>not json</html>")

    with pytest.raises(FederatedSearchError, match="could not read"):
        await source.search(query())


@pytest.mark.asyncio
async def test_a_hit_with_no_uri_is_a_typed_error_not_a_keyerror(httpx_mock, source):
    httpx_mock.add_response(json={"count": 1, "hits": [{"aLabel": "no uri here"}]})

    with pytest.raises(FederatedSearchError, match="no URI"):
        await source.search(query())


def test_title_strips_a_contributor_that_already_ends_in_a_period():
    """Real case from id.loc.gov: the heading "Magida, Arthur J." ends in a
    period, so the separator is a bare space, not ". ". Building the prefix as
    contributor + ". " misses every heading ending in an initial."""
    hit = {
        "aLabel": "Magida, Arthur J. Two wheels to freedom",
        "vLabel": "Magida, Arthur J. Story of a young Jew, wartime resistance",
        "more": {"contributors": ["Magida, Arthur J."]},
    }
    assert title_from(hit) == "Two wheels to freedom"


def test_title_survives_an_access_point_that_is_only_the_contributor():
    """Nothing left after stripping means the heading is all we have."""
    hit = {
        "aLabel": "Magida, Arthur J.",
        "vLabel": "",
        "more": {"contributors": ["Magida, Arthur J."]},
    }
    assert title_from(hit) == "Magida, Arthur J."
