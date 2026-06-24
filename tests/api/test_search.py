from bluecore_api.app.services.search import format_query
from bluecore_api.app.utils.serialize.html import resource_section, resource_title
from bluecore_models.models import OtherResource, Work
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from types import SimpleNamespace
import json
import pathlib
import pytest


def test_search_helpers_tolerate_list_shaped_jsonld():
    # Some OtherResources store JSON-LD as a top-level array of nodes (or an
    # {"@graph": [...]} wrapper) rather than a single object. The HTML search
    # helpers must derive a section/title from these without raising
    # AttributeError: 'list' object has no attribute 'get'.
    array_data = [
        {
            "@id": "https://example.org/hub/1",
            "@type": ["http://id.loc.gov/ontologies/bibframe/Hub"],
            "rdfs:label": "Stephen King hub",
        },
        {"@id": "https://example.org/concept/2", "@type": ["skos:Concept"]},
    ]
    graph_data = {"@graph": array_data}

    for data in (array_data, graph_data):
        resource = SimpleNamespace(data=data, uri="https://example.org/hub/1")
        assert resource_section(resource) == "Hubs"
        assert resource_title(resource) == "Stephen King hub"

    # A plain object is unchanged by the normalization.
    obj = SimpleNamespace(data={"title": {"mainTitle": "It"}}, uri="https://ex/it")
    assert resource_title(obj) == "It"


def test_resource_title_resolves_labels_across_namespaces():
    # Standalone authority records (from id.loc.gov) carry their label under varied
    # predicates: madsrdf:, skos:, or fully-expanded URIs, not just the bibframe
    # `mads:`/`rdfs:` prefixes. All must resolve to the readable label instead of
    # falling back to the bare @id tail (e.g. "n2010185030").
    cases = {
        "madsrdf:authoritativeLabel": "Smith, John, 1970-",
        "http://www.loc.gov/mads/rdf/v1#authoritativeLabel": "Doe, Jane",
        "skos:prefLabel": "Cats",
        "http://www.w3.org/2004/02/skos/core#prefLabel": "Dogs",
        "rdfs:label": "Plain Label",
    }
    for key, value in cases.items():
        resource = SimpleNamespace(
            data={
                "@id": "https://id.loc.gov/authorities/names/n2010185030",
                "@type": ["http://www.loc.gov/mads/rdf/v1#PersonalName"],
                key: value,
            },
            uri="https://id.loc.gov/authorities/names/n2010185030",
        )
        assert resource_title(resource) == value

    # With no label predicate at all it still falls back to the @id tail.
    bare = SimpleNamespace(
        data={"@id": "https://id.loc.gov/authorities/names/n2010185030"},
        uri="https://id.loc.gov/authorities/names/n2010185030",
    )
    assert resource_title(bare) == "n2010185030"


def test_format_query():
    assert format_query("") == ""
    assert format_query("hello world") == "hello & world"
    assert format_query(" hello world") == "hello & world"
    assert format_query("hello  world") == "hello & world"
    assert format_query("hello | world") == "hello | world"
    assert format_query("hello|world") == "hello | world"
    assert format_query("hello |world test") == "hello | world & test"
    assert format_query("hello 1 world 2") == "hello & 1 & world & 2"
    assert format_query('"hello world" test') == "hello <-> world & test"
    assert format_query('" hello world " test') == "hello <-> world & test"
    assert (
        format_query('test "hello world" | "phrase search terms"')
        == "test & hello <-> world | phrase <-> search <-> terms"
    )
    assert (
        format_query("bluecore:bf2:Monograph:Work")
        == "bluecore & bf2 & Monograph & Work"
    )
    assert (
        format_query('"Ocean Becoming : Pacific pavements"')
        == "Ocean <-> Becoming <-> \\: <-> Pacific <-> pavements"
    )
    assert (
        format_query('"phrase with ampersand & test"')
        == "phrase <-> with <-> ampersand <-> \\& <-> test"
    )
    assert (
        format_query('"phrase with ampersand&test2"')
        == "phrase <-> with <-> ampersand\\&test2"
    )
    assert (
        format_query('"phrase with ampersand& test3"')
        == "phrase <-> with <-> ampersand\\& <-> test3"
    )
    assert (
        format_query('"phrase with ampersand &test4"')
        == "phrase <-> with <-> ampersand <-> \\&test4"
    )
    assert (
        format_query('"phrase with double ampersand && test"')
        == "phrase <-> with <-> double <-> ampersand <-> \\&\\& <-> test"
    )
    assert (
        format_query('"phrase with | or operator test"')
        == "phrase <-> with <-> \\| <-> or <-> operator <-> test"
    )
    assert (
        format_query('"phrase with|or operator test2"')
        == "phrase <-> with\\|or <-> operator <-> test2"
    )
    assert (
        format_query('"phrase with| or operator test3"')
        == "phrase <-> with\\| <-> or <-> operator <-> test3"
    )
    assert (
        format_query('"phrase with |or operator test4"')
        == "phrase <-> with <-> \\|or <-> operator <-> test4"
    )
    assert format_query("hello worl*") == "hello & worl:*"
    assert format_query("*leading wildcard test") == "leading & wildcard & test"
    assert format_query('"hell* worl*"') == "hell:* <-> worl:*"
    assert format_query('"inval * wildcard *"') == "inval <-> wildcard"
    assert format_query('"inval*wildcard test2"') == "inval:* <-> wildcard <-> test2"
    assert format_query('"inval *wildcard test3"') == "inval <-> wildcard <-> test3"
    assert (
        format_query('"*phrase leading wildcard test"')
        == "phrase <-> leading <-> wildcard <-> test"
    )
    assert (
        format_query('"double wild card** test"')
        == "double <-> wild <-> card:* <-> test"
    )
    assert (
        format_query('"double wild card* * test2"')
        == "double <-> wild <-> card:* <-> test2"
    )
    assert (
        format_query('"double wild card* *test3"')
        == "double <-> wild <-> card:* <-> test3"
    )
    assert format_query("http://uri.org/test") == "http\\://uri.org/test"
    assert format_query("colon : test2") == "colon & test2"
    assert format_query("colon: test3") == "colon & test3"
    assert format_query("colon :test4") == "colon & test4"
    assert (
        format_query('"phrase colon escape : test"')
        == "phrase <-> colon <-> escape <-> \\: <-> test"
    )
    assert (
        format_query('"phrase colon escape:test2"')
        == "phrase <-> colon <-> escape\\:test2"
    )
    assert (
        format_query('"phrase colon escape: test3"')
        == "phrase <-> colon <-> escape\\: <-> test3"
    )
    assert (
        format_query('"phrase colon escape :test4"')
        == "phrase <-> colon <-> escape <-> \\:test4"
    )
    assert (
        format_query("trailing and operator test &")
        == "trailing & and & operator & test"
    )
    assert (
        format_query("trailing or operator test|") == "trailing & or & operator & test"
    )
    # A bare "&" outside a phrase is treated as a separator (AND), not emitted as a
    # stray operator that would make an invalid tsquery ("cat & & & mouse").
    assert format_query("cat & mouse") == "cat & mouse"
    assert format_query("cat&mouse") == "cat & mouse"
    assert format_query("cat && mouse") == "cat & mouse"
    # Escaped ampersands inside a phrase are still preserved.
    assert format_query('"cat & mouse"') == "cat <-> \\& <-> mouse"


test_work_uuid = "370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
test_work_bluecore_uri = f"https://api.sinopia.io/resources/{test_work_uuid}"


def add_data(db_session: Session):
    work_data = json.load(pathlib.Path("tests/blue-core-work.jsonld").open())

    db_session.add(
        Work(
            id=1,
            uuid=test_work_uuid,
            uri=test_work_bluecore_uri,
            data=work_data,
        ),
    )


def add_other_resources(db_session: Session):
    eng = json.load(pathlib.Path("tests/blue-core-other-resources.json").open())
    kor = json.load(pathlib.Path("tests/blue-core-other-resources2.json").open())
    db_session.add(
        OtherResource(
            is_profile=True,
            uri="https://api.sinopia.io/profiles/test-profile",
            data=eng,
        ),
    )
    db_session.add(
        OtherResource(
            is_profile=True,
            uri="https://api.sinopia.io/profiles/test-profile2",
            data=kor,
        ),
    )
    db_session.commit()


def test_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mit"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1
    assert (
        result["links"]["first"]
        == "https://bcld.info/api/search/?limit=20&offset=0&q=kumae+chedo+mit&type=all"
    )


def test_search_with_ampersand_does_not_error(client: TestClient, db_session: Session):
    add_data(db_session)

    # A literal "&" in the query used to build invalid tsquery ("cat & & & mouse")
    # and 500. It should now be treated as a separator and run cleanly.
    json_resp = client.get("/search/", params={"q": "cat & mouse", "type": "instances"})
    assert json_resp.status_code == 200

    html_resp = client.get("/search", params={"q": "cat & mouse", "type": "all"})
    assert html_resp.status_code == 200


def test_search_html(client: TestClient, db_session: Session):
    add_data(db_session)

    # The public, human-facing search (GET /search, distinct from JSON /search/).
    response = client.get("/search", params={"q": "kumae chedo mit"})
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert "Search results" in response.text
    # The single matching Work is grouped and linked to its dereferenceable URL.
    assert "1 result" in response.text
    assert test_work_bluecore_uri in response.text


def _timeout_error():
    from sqlalchemy.exc import OperationalError

    return OperationalError(
        "SELECT ...",
        {},
        Exception("canceling statement due to statement timeout"),
    )


def test_search_html_too_broad(client: TestClient, db_session: Session, monkeypatch):
    add_data(db_session)
    # Commit so the timeout handler's rollback doesn't drop the test data. In
    # production search only reads, so the rollback has nothing to lose.
    db_session.commit()

    # Simulate a query that exceeds its statement_timeout: the full-text search is
    # cancelled by Postgres. The HTML view must return 200 with a "too broad"
    # message instead of hanging or 500-ing.
    real_execute = db_session.execute

    def flaky_execute(statement, *args, **kwargs):
        if "ts_rank" in str(statement) or "count(*)" in str(statement):
            raise _timeout_error()
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", flaky_execute)

    response = client.get("/search", params={"q": "c*", "type": "all"})
    assert response.status_code == 200
    assert "too broad" in response.text
    # No results / no crash.
    assert test_work_bluecore_uri not in response.text


def test_search_json_too_broad(client: TestClient, db_session: Session, monkeypatch):
    add_data(db_session)
    db_session.commit()

    # The JSON API returns a 422 (rather than hanging) when a search is too broad.
    real_execute = db_session.execute

    def flaky_execute(statement, *args, **kwargs):
        if "ts_rank" in str(statement) or "count(*)" in str(statement):
            raise _timeout_error()
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", flaky_execute)

    response = client.get("/search/", params={"q": "c*", "type": "all"})
    assert response.status_code == 422
    assert "too broad" in response.json()["detail"]


def test_search_html_empty_query(client: TestClient, db_session: Session):
    add_data(db_session)

    # A blank query must not match/scan the entire database (which hangs in
    # production); it short-circuits without touching the DB and renders the
    # initial prompt rather than a "0 results" / "No results" message.
    for params in ({"type": "all", "q": ""}, {"type": "works"}, {"type": "instances"}):
        response = client.get("/search", params=params)
        assert response.status_code == 200
        assert response.headers["Content-Type"].startswith("text/html")
        assert "Enter a search above to see results." in response.text
        assert "No results." not in response.text
        assert "result for" not in response.text


def test_or_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mi | mit"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1
    assert result["links"]["first"] == (
        "https://bcld.info/api/search/?limit=20&offset=0&q=kumae+chedo+mi+%7C+mit&type=all"
    )


def test_phrase_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": '"kumae chedo mit"'})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1


def test_wildcard_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mi*"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1
    assert result["links"]["first"] == (
        "https://bcld.info/api/search/?limit=20&offset=0&q=kumae+chedo+mi%2A&type=all"
    )


def test_search_incomplete_word(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mi"})
    result = response.json()
    assert len(result["results"]) == 0
    assert result["total"] == 0


def test_search_works(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mit", "type": "works"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1
    assert (
        result["links"]["first"]
        == "https://bcld.info/api/search/?limit=20&offset=0&q=kumae+chedo+mit&type=works"
    )


def test_search_instances(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get(
        "/search/", params={"q": "kumae chedo mit", "type": "instances"}
    )
    result = response.json()
    assert (
        len(result["results"]) == 0
    )  # We didn't add any instances, so should return 0
    assert result["total"] == 0


def test_search_keyword_and_phrase(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get(
        "/search/", params={"q": 'Chaesaeng "kumae chedo mit"', "type": "all"}
    )
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1


def test_search_diacritics(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "Chaesaeng enŏji", "type": "all"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1


def test_uri(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get(
        "/search/", params={"q": test_work_bluecore_uri, "type": "all"}
    )
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1


def test_bad_query_trailing_operator(client: TestClient, db_session: Session):
    add_data(db_session)

    # trailing | operator is ignored
    response = client.get("/search/", params={"q": "kumae chedo mit |"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["total"] == 1


def test_bad_query_colon_in_phrase(client: TestClient, db_session: Session):
    add_data(db_session)

    # kumae <-> \: <-> chedo <-> mit doesn't match because of the escaped colon
    response = client.get("/search/", params={"q": '"kumae : chedo mit"'})
    result = response.json()
    assert len(result["results"]) == 0
    assert result["total"] == 0


def test_search_profile_no_match(client: TestClient, db_session: Session):
    response = client.get("/search/profile", params={})
    result = response.json()
    assert len(result["results"]) == 0  # No profiles added, should return 0
    assert result["total"] == 0


def test_search_profile(client: TestClient, db_session: Session):
    add_other_resources(db_session)

    response = client.get(
        "/search/profile", params={"q": "id.loc.gov/ontologies/bibframe/language"}
    )
    result = response.json()
    assert len(result["results"]) == 2
    assert result["results"][0]["uri"] == "https://api.sinopia.io/profiles/test-profile"
    assert result["total"] == 2
    assert (
        result["links"]["first"]
        == "https://bcld.info/api/search/profile/?limit=20&offset=0&q=id.loc.gov%2Fontologies%2Fbibframe%2Flanguage"
    )


def test_search_profile_limit(client: TestClient, db_session: Session):
    add_other_resources(db_session)

    response = client.get(
        "/search/profile",
        params={"q": "id.loc.gov/ontologies/bibframe/language", "limit": 1},
    )
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"] == "https://api.sinopia.io/profiles/test-profile"
    assert result["total"] == 2


_BF = "http://id.loc.gov/ontologies/bibframe/"
_RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"


def _node(uri: str, bf_type: str, label: str) -> list[dict]:
    return [
        {
            "@id": uri,
            "@type": [f"{_BF}{bf_type}"],
            _RDFS_LABEL: [{"@value": label}],
        }
    ]


def test_search_json_other_resources_excludes_profiles(
    client: TestClient, db_session: Session
):
    # The new `other_resources` search type returns non-profile OtherResources
    # (authorities, agents, subjects) and excludes profiles.
    term = "otherresourcetoken"
    topic_uri = "https://id.loc.gov/x/topic-1"
    db_session.add(
        OtherResource(
            is_profile=False, uri=topic_uri, data=_node(topic_uri, "Topic", f"{term} a")
        )
    )
    db_session.add(
        OtherResource(
            is_profile=True,
            uri="https://api.sinopia.io/profiles/excluded",
            data={"title": f"{term} profile"},
        )
    )
    db_session.commit()

    response = client.get("/search/", params={"q": term, "type": "other_resources"})
    result = response.json()
    assert response.status_code == 200
    assert result["total"] == 1
    assert result["results"][0]["uri"] == topic_uri


def test_search_json_other_resources_list_shaped_data(
    client: TestClient, db_session: Session
):
    # OtherResources store JSON-LD as a top-level array (graph), not a dict. The
    # JSON /search/ response model must accept that shape rather than 500 with a
    # ResponseValidationError ("Input should be a valid dictionary").
    term = "listshapedtoken"
    uri = "https://id.loc.gov/x/hub-list"
    db_session.add(
        OtherResource(
            is_profile=False,
            uri=uri,
            data=_node(uri, "Hub", f"{term} a"),  # _node returns a list
        )
    )
    db_session.commit()

    response = client.get("/search/", params={"q": term, "type": "other_resources"})
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 1
    assert result["results"][0]["uri"] == uri


def test_search_html_other_resources_type(client: TestClient, db_session: Session):
    term = "otherresourcehtml"
    topic_uri = "https://id.loc.gov/x/topic-html"
    db_session.add(
        OtherResource(
            is_profile=False, uri=topic_uri, data=_node(topic_uri, "Topic", f"{term} a")
        )
    )
    db_session.commit()

    response = client.get("/search", params={"q": term, "type": "other_resources"})
    assert response.status_code == 200
    assert topic_uri in response.text
    # A single-type search renders one panel (no "Works & Instances" panel title).
    assert "Works &amp; Instances" not in response.text


def test_search_html_all_paginates_panels_independently(
    client: TestClient, db_session: Session
):
    # An "all" search runs two separately-paginated searches. With a page size of 1
    # and two matches in each scope, each panel must offer its own "next" link that
    # pages only that scope (primary_offset / secondary_offset), preserving the other.
    term = "alltoken"
    for i in (2, 3):
        uri = f"https://bcld.info/works/work-{i}"
        db_session.add(
            Work(
                id=i,
                uuid=f"00000000-0000-0000-0000-00000000000{i}",
                uri=uri,
                data=_node(uri, "Work", f"{term} work {i}"),
            )
        )
    for i in (4, 5):
        uri = f"https://id.loc.gov/x/topic-{i}"
        db_session.add(
            OtherResource(
                id=i,
                is_profile=False,
                uri=uri,
                data=_node(uri, "Topic", f"{term} topic {i}"),
            )
        )
    db_session.commit()

    response = client.get("/search", params={"q": term, "type": "all", "limit": 1})
    assert response.status_code == 200
    body = response.text
    # Two independently-titled panels.
    assert ">Works &amp; Instances</h2>" in body
    assert ">Other Resources</h2>" in body
    # Each panel pages on its own offset param.
    assert "primary_offset=1" in body
    assert "secondary_offset=1" in body


def test_search_html_partial_returns_single_panel_fragment(
    client: TestClient, db_session: Session
):
    # The per-panel pagination JS requests one panel with `partial=<key>`. The
    # response is just that panel's <section> fragment (no full page / base layout),
    # so it can be swapped in place without reloading.
    term = "partialtoken"
    work_uri = "https://bcld.info/works/work-partial"
    db_session.add(
        Work(
            id=42,
            uuid="00000000-0000-0000-0000-000000000042",
            uri=work_uri,
            data=_node(work_uri, "Work", f"{term} a"),
        )
    )
    topic_uri = "https://id.loc.gov/x/topic-partial"
    db_session.add(
        OtherResource(
            id=43,
            is_profile=False,
            uri=topic_uri,
            data=_node(topic_uri, "Topic", f"{term} b"),
        )
    )
    db_session.commit()

    response = client.get(
        "/search", params={"q": term, "type": "all", "partial": "primary"}
    )
    assert response.status_code == 200
    body = response.text
    # Just the Works/Instances panel fragment...
    assert 'data-panel="primary"' in body
    assert work_uri in body
    # ...not the full page, and not the other panel.
    assert "<html" not in body
    assert 'data-panel="secondary"' not in body
    assert topic_uri not in body


def test_search_pagination_is_stable_and_disjoint(
    client: TestClient, db_session: Session
):
    # Equal-ranked results must order deterministically (id tiebreaker) so paging
    # doesn't reshuffle or repeat rows from page to page.
    term = "stableordertoken"
    for i in range(5):
        uri = f"https://dev.bcld.info/works/stable-{i}"
        db_session.add(
            Work(
                id=8000 + i,
                uuid=f"00000000-0000-0000-0000-0000000080{i:02d}",
                uri=uri,
                data=_node(uri, "Work", f"{term} item"),
            )
        )
    db_session.commit()

    def page_uris(offset: int) -> list[str]:
        resp = client.get(
            "/search/",
            params={"q": term, "type": "works", "limit": 2, "offset": offset},
        )
        return [r["uri"] for r in resp.json()["results"]]

    pages = page_uris(0) + page_uris(2) + page_uris(4)
    assert len(pages) == 5  # full coverage, nothing skipped
    assert len(set(pages)) == 5  # no row repeats across pages
    # Re-fetching a page returns the same rows in the same order.
    assert page_uris(0) == pages[:2]


if __name__ == "__main__":
    pytest.main()
