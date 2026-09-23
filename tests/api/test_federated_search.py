"""GET /search/federated -- the grouped envelope.

Stage 1 covers the Blue Core source only, so these tests establish the shape
and, most importantly, that GET /search/ is untouched by any of it.
"""

import json
import pathlib

import httpx
import pytest
from bluecore_models.models import Hub, Instance, Work
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

TITLE = "federatedtesttitle"


@pytest.fixture(autouse=True)
def local_only(monkeypatch):
    """Default every test here to the local source.

    Without this a test that forgets to register a response would reach out to
    the real id.loc.gov, which is both flaky in CI and exactly the kind of
    unattributed traffic this feature is supposed to avoid. Tests that want the
    remote source opt in with `with_loc`.
    """
    monkeypatch.setenv("FEDERATED_SEARCH_SOURCES", "bluecore")


@pytest.fixture
def with_loc(monkeypatch):
    monkeypatch.setenv("FEDERATED_SEARCH_SOURCES", "bluecore,loc")


@pytest.fixture
def searchable(db_session: Session) -> None:
    """One Work, Instance and Hub sharing a title no other fixture uses."""
    models = (Work, Instance, Hub)
    names = ("works", "instances", "hubs")
    for id_, (model, name) in enumerate(zip(models, names, strict=True), start=91):
        uri = f"https://bcld.info/{name}/00000000-0000-0000-0000-0000000000{id_}"
        db_session.add(
            model(
                id=id_,
                uuid=f"00000000-0000-0000-0000-0000000000{id_}",
                uri=uri,
                data={
                    "@id": uri,
                    "@type": model.__name__,
                    "title": {"@type": "Title", "mainTitle": TITLE},
                },
            )
        )
    db_session.commit()


def _group(payload: dict, source_id: str) -> dict:
    return next(g for g in payload["sources"] if g["id"] == source_id)


def test_results_are_grouped_by_source(client: TestClient, searchable: None):
    payload = client.get("/search/federated", params={"q": TITLE}).json()

    assert [g["id"] for g in payload["sources"]] == ["bluecore"]
    group = _group(payload, "bluecore")
    assert group["status"] == "ok"
    assert group["error"] is None
    assert group["total"] == 3
    assert group["total_is_exact"] is True
    assert len(group["results"]) == 3
    assert payload["partial"] is False


def test_local_results_are_labelled_as_ours(client: TestClient, searchable: None):
    payload = client.get("/search/federated", params={"q": TITLE}).json()

    for result in _group(payload, "bluecore")["results"]:
        assert result["source"] == "bluecore"
        assert result["source_label"] == "Blue Core"
        # A Blue Core record is trivially already in Blue Core; clients should
        # not have to special-case which sources can fill this in.
        assert result["local_uri"] == result["uri"]
        assert result["id"] is not None
        assert result["data"]["@context"].endswith("/context.jsonld")


def test_explicit_nulls_are_kept(client: TestClient, searchable: None):
    """Unlike the rest of the API this endpoint does not drop None.

    "we looked and there is no copy" and "we did not look" have to be
    distinguishable, and an absent key cannot say either.
    """
    payload = client.get("/search/federated", params={"q": TITLE}).json()

    result = _group(payload, "bluecore")["results"][0]
    assert "proxy_uri" in result and result["proxy_uri"] is None
    assert "rank" in result and result["rank"] is None
    assert "error" in _group(payload, "bluecore")


def test_type_filter_is_honored(client: TestClient, searchable: None):
    payload = client.get(
        "/search/federated", params={"q": TITLE, "type": "works"}
    ).json()

    group = _group(payload, "bluecore")
    assert group["total"] == 1
    assert group["results"][0]["type"] == "works"


def test_paging_links_are_per_source(client: TestClient, searchable: None):
    payload = client.get(
        "/search/federated", params={"q": TITLE, "limit": 2, "offset": 2}
    ).json()

    links = _group(payload, "bluecore")["links"]
    base = "https://bcld.info/api/search/federated"
    assert links["first"] == f"{base}?limit=2&offset=0&q={TITLE}&type=all"
    assert links["prev"] == f"{base}?limit=2&offset=0&q={TITLE}&type=all"
    # A short final page means there is nothing after it.
    assert links["next"] is None


def test_unknown_source_is_rejected(client: TestClient):
    response = client.get("/search/federated", params={"q": TITLE, "sources": "nope"})

    assert response.status_code == 422
    assert "Unknown source" in response.json()["detail"]


def test_sources_parameter_narrows(client: TestClient, searchable: None):
    payload = client.get(
        "/search/federated", params={"q": TITLE, "sources": "bluecore"}
    ).json()

    assert [g["id"] for g in payload["sources"]] == ["bluecore"]


def test_plain_search_endpoint_is_unchanged(client: TestClient, searchable: None):
    """Regression guard. GET /search/ is what sinopia_editor calls today and
    what the MCP `search` tool exposes; federated search must not touch it."""
    payload = client.get("/search/", params={"q": TITLE}).json()

    assert sorted(payload) == ["links", "results", "total"]
    assert payload["total"] == 3
    assert sorted(payload["results"][0]) == [
        "created_at",
        "data",
        "id",
        "type",
        "updated_at",
        "uri",
        "uuid",
    ]
    assert (
        payload["links"]["first"]
        == f"https://bcld.info/api/search/?limit=20&offset=0&q={TITLE}&type=all"
    )


# --- With the Library of Congress source ---------------------------------------
def _loc_payload() -> dict:
    with pathlib.Path("tests/loc-suggest2-works.json").open() as fo:
        return json.load(fo)


def test_both_sources_get_their_own_group(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    httpx_mock.add_response(json=_loc_payload())

    payload = client.get(
        "/search/federated", params={"q": TITLE, "type": "works"}
    ).json()

    assert [g["id"] for g in payload["sources"]] == ["bluecore", "loc"]
    assert _group(payload, "bluecore")["total_is_exact"] is True
    assert _group(payload, "loc")["total_is_exact"] is False
    # The top-level total sums the groups and says so: an LC record already
    # copied into Blue Core is counted on both sides.
    assert payload["total"] == 1 + 190
    assert payload["total_is_estimate"] is True


def test_narrowing_to_bluecore_makes_no_outbound_request(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    client.get("/search/federated", params={"q": TITLE, "sources": "bluecore"})

    assert httpx_mock.get_requests() == []


def test_outbound_requests_identify_us(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    """id.loc.gov's robots.txt warns it blocks clients it cannot identify, and
    a block would land on every id.loc.gov user at the institution."""
    httpx_mock.add_response(json=_loc_payload())

    client.get("/search/federated", params={"q": TITLE, "type": "works"})

    user_agent = httpx_mock.get_requests()[0].headers["user-agent"]
    assert user_agent.startswith("BlueCore-API/")
    assert "bcld.info" in user_agent


def test_a_timed_out_source_degrades_the_page_not_the_request(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    """The most important test here.

    If a dead source came back as an empty result set, a cataloger would read
    it as "no such record exists" and hand-catalogue a duplicate. The failure
    has to be visible and the other sources have to survive it.
    """
    httpx_mock.add_exception(httpx.ReadTimeout("slow"))

    response = client.get("/search/federated", params={"q": TITLE, "type": "works"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["partial"] is True

    loc = _group(payload, "loc")
    assert loc["status"] == "error"
    assert loc["results"] == []
    assert "Could not reach" in loc["error"]

    bluecore = _group(payload, "bluecore")
    assert bluecore["status"] == "ok"
    assert len(bluecore["results"]) == 1


def test_an_upstream_error_is_reported_in_words_a_cataloger_can_read(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    httpx_mock.add_response(status_code=503)

    payload = client.get(
        "/search/federated", params={"q": TITLE, "type": "works"}
    ).json()

    loc = _group(payload, "loc")
    assert loc["status"] == "error"
    assert loc["error"] == "Library of Congress returned HTTP 503."
    assert "Traceback" not in loc["error"]


def test_external_results_carry_provenance_not_a_blue_core_identity(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    httpx_mock.add_response(json=_loc_payload())

    payload = client.get(
        "/search/federated", params={"q": TITLE, "type": "works"}
    ).json()

    result = _group(payload, "loc")["results"][0]
    assert result["source"] == "loc"
    # The real LC URI, never a Blue Core proxy URL dressed up as one: a client
    # that copied from `uri` must not silently succeed against the wrong thing.
    assert result["uri"] == "http://id.loc.gov/resources/works/13337906"
    assert result["id"] is None
    assert result["uuid"] is None
    # Stage 5 fills this in; until then it is explicitly "we did not look".
    assert result["local_uri"] is None
    assert result["data"]["title"][0]["mainTitle"] == "Moby-Dick, or, The whale"


# --- Caching and "already in Blue Core" ----------------------------------------
LOC_WORK_URI = "http://id.loc.gov/resources/works/13337906"


def test_repeat_searches_make_one_outbound_request(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    """Politeness, and the metric that makes the cost argument.

    LC serves these with cache-control: public, max-age=2419200, so a short
    local TTL is conservative.
    """
    httpx_mock.add_response(json=_loc_payload(), is_reusable=True)

    for _ in range(3):
        client.get("/search/federated", params={"q": TITLE, "type": "works"})

    assert len(httpx_mock.get_requests()) == 1


def test_an_external_hit_we_already_hold_is_flagged(
    client: TestClient, db_session: Session, with_loc: None, httpx_mock
):
    """Without this, the first thing federated search does is manufacture
    duplicates: two catalogers copy the same LC work and Blue Core ends up with
    two unrelated resources derived from it."""
    httpx_mock.add_response(json=_loc_payload())
    copied_uri = "https://bcld.info/works/00000000-0000-0000-0000-000000000095"
    db_session.add(
        Work(
            id=95,
            uuid="00000000-0000-0000-0000-000000000095",
            uri=copied_uri,
            data={
                "@id": copied_uri,
                "@type": "Work",
                "title": {"@type": "Title", "mainTitle": "Moby-Dick"},
                "adminMetadata": [
                    {
                        "@type": "AdminMetadata",
                        "derivedFrom": {"@id": LOC_WORK_URI},
                    }
                ],
            },
        )
    )
    db_session.commit()

    payload = client.get(
        "/search/federated", params={"q": TITLE, "type": "works"}
    ).json()

    results = {r["uri"]: r for r in _group(payload, "loc")["results"]}
    assert results[LOC_WORK_URI]["local_uri"] == copied_uri
    # Every other hit is explicitly "we looked and we do not have it".
    others = [r for uri, r in results.items() if uri != LOC_WORK_URI]
    assert others and all(r["local_uri"] is None for r in others)


def test_provenance_matches_across_http_and_https(
    client: TestClient, db_session: Session, with_loc: None, httpx_mock
):
    """id.loc.gov searches return http:// URIs but redirect browsers to
    https://, so which form got stored depends on how the record arrived."""
    httpx_mock.add_response(json=_loc_payload())
    copied_uri = "https://bcld.info/works/00000000-0000-0000-0000-000000000096"
    db_session.add(
        Work(
            id=96,
            uuid="00000000-0000-0000-0000-000000000096",
            uri=copied_uri,
            data={
                "@id": copied_uri,
                "@type": "Work",
                "title": {"@type": "Title", "mainTitle": "Moby-Dick"},
                "adminMetadata": [
                    {
                        "@type": "AdminMetadata",
                        "derivedFrom": {
                            "@id": LOC_WORK_URI.replace("http://", "https://")
                        },
                    }
                ],
            },
        )
    )
    db_session.commit()

    payload = client.get(
        "/search/federated", params={"q": TITLE, "type": "works"}
    ).json()

    results = {r["uri"]: r for r in _group(payload, "loc")["results"]}
    assert results[LOC_WORK_URI]["local_uri"] == copied_uri


# --- HTML view -----------------------------------------------------------------
HTML = {"Accept": "text/html"}


def test_html_shows_a_section_per_source(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    """Makes the feature demonstrable in a browser with no editor changes."""
    httpx_mock.add_response(json=_loc_payload())

    response = client.get(
        "/search/federated", params={"q": TITLE, "type": "works"}, headers=HTML
    )

    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "Blue Core" in body
    assert "Library of Congress" in body
    # Titles come out of the same helper the rest of the HTML views use.
    assert "Moby-Dick, or, The whale" in body


def test_html_says_a_source_failed_rather_than_showing_nothing(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    httpx_mock.add_response(status_code=503)

    body = client.get(
        "/search/federated", params={"q": TITLE, "type": "works"}, headers=HTML
    ).text

    assert "Library of Congress returned HTTP 503." in body
    # And the working source is still on the page.
    assert TITLE in body


def test_json_is_still_the_default(client: TestClient, searchable: None, httpx_mock):
    response = client.get("/search/federated", params={"q": TITLE})

    assert response.headers["content-type"].startswith("application/json")


# --- Experiment counters --------------------------------------------------------
def test_metrics_count_what_the_experiment_needs(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    """The deciding number is distinct external records actually opened, set
    against the size of the corpus a bulk load would bring in."""
    httpx_mock.add_response(json=_loc_payload(), is_reusable=True)

    client.get("/search/federated", params={"q": TITLE, "type": "works"})
    client.get("/search/federated", params={"q": TITLE, "type": "works"})

    counts = client.get("/search/federated/metrics").json()
    assert counts["searches"] == 2
    assert counts["source_outcomes"] == {"bluecore:ok": 2, "loc:ok": 2}
    # Three distinct LC records, seen twice: the count is of records, not rows.
    assert counts["distinct_external_records_seen"] == 3
    # Nobody opened one, so nothing has been touched.
    assert counts["distinct_external_records_fetched"] == 0
    # The second search was served from cache.
    assert counts["upstream_cache_hit_rate"] == 0.5


def test_a_failed_source_is_counted_as_such(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    httpx_mock.add_response(status_code=503)

    client.get("/search/federated", params={"q": TITLE, "type": "works"})

    counts = client.get("/search/federated/metrics").json()
    assert counts["source_outcomes"] == {"bluecore:ok": 1, "loc:error": 1}


def test_the_local_search_page_offers_a_way_in(client: TestClient, searchable: None):
    """The only route into federated search from the UI. Without it the
    experiment measures people who already knew the URL."""
    body = client.get("/search", params={"q": TITLE}).text

    assert "Also search the Library of Congress" in body
    assert f"/search/federated?q={TITLE}&amp;type=all" in body


def test_searching_again_from_the_federated_page_stays_federated(
    client: TestClient, searchable: None, with_loc: None, httpx_mock
):
    """base.html is shared, so without an override the header form would throw
    a cataloger back to the local-only search on their next query."""
    httpx_mock.add_response(json=_loc_payload())

    body = client.get(
        "/search/federated", params={"q": TITLE, "type": "works"}, headers=HTML
    ).text

    # root_path prefixes it, the same way the local search form is built.
    assert 'action="/api/search/federated"' in body
