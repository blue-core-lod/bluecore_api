"""Exact identifier lookups through the Identifier search scope."""

from bluecore_models.models import ResourceBase, Work
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from bluecore_api.app.routes.search import identifier_match

IDENTIFIERS_INDEX = "index_resource_base_on_identifiers"


# Adds a Work with the given identifiedBy and returns its URI
def add_work(db_session: Session, number: int, identified_by: list[dict]) -> str:
    uri = f"https://bcld.info/works/00000000-0000-0000-0000-0000000002{number:02d}"
    db_session.add(
        Work(
            id=950 + number,
            uuid=f"00000000-0000-0000-0000-0000000002{number:02d}",
            uri=uri,
            data={"@id": uri, "@type": "Work", "identifiedBy": identified_by},
        )
    )
    db_session.commit()
    return uri


# Runs an identifier search and returns the URIs it found
def search_uris(client: TestClient, identifier: str) -> list[str]:
    response = client.get("/search/", params={"q": identifier, "scope": "identifier"})
    assert response.status_code == 200, response.text
    return [result["uri"] for result in response.json()["results"]]


def test_lccn_with_spaces_is_found(client: TestClient, db_session: Session):
    uri = add_work(db_session, 1, [{"@type": "Lccn", "rdf:value": "sn 85009985 "}])
    assert search_uris(client, "sn85009985") == [uri]
    assert search_uris(client, "lccn:sn85009985") == [uri]
    assert search_uris(client, "LCCN: sn 85009985") == [uri]


def test_hyphenated_lccn_is_found(client: TestClient, db_session: Session):
    uri = add_work(db_session, 2, [{"@type": "Lccn", "rdf:value": "n78890351"}])
    assert search_uris(client, "lccn:n78-890351") == [uri]


def test_prefix_only_searches_that_scheme(client: TestClient, db_session: Session):
    lccn_uri = add_work(db_session, 3, [{"@type": "Lccn", "rdf:value": "20965281"}])
    issn_uri = add_work(db_session, 4, [{"@type": "Issn", "rdf:value": "20965281"}])
    assert search_uris(client, "lccn:20965281") == [lccn_uri]
    assert search_uris(client, "20965281") == [lccn_uri, issn_uri]


def test_isbn_matches_either_form(client: TestClient, db_session: Session):
    uri = add_work(db_session, 5, [{"@type": "Isbn", "rdf:value": "0878880690"}])
    assert search_uris(client, "isbn:978-0-87888-069-0") == [uri]
    assert search_uris(client, "isbn:0-87888-069-0") == [uri]
    assert search_uris(client, "9780878880690") == [uri]


def test_issn_with_or_without_hyphen(client: TestClient, db_session: Session):
    uri = add_work(db_session, 6, [{"@type": "Issn", "rdf:value": "0047-1607"}])
    assert search_uris(client, "issn:0047-1607") == [uri]
    assert search_uris(client, "00471607") == [uri]


def test_doi_with_a_colon_is_found(client: TestClient, db_session: Session):
    uri = add_work(db_session, 7, [{"@type": "Doi", "rdf:value": "10.1000/X:Y"}])
    assert search_uris(client, "doi:10.1000/x:y") == [uri]
    assert search_uris(client, "10.1000/x:y") == [uri]


def test_other_identifiers_are_not_searchable(client: TestClient, db_session: Session):
    add_work(db_session, 8, [{"@type": "Local", "rdf:value": "SERIALSET-02254"}])
    assert search_uris(client, "SERIALSET-02254") == []
    assert search_uris(client, "local:SERIALSET-02254") == []


def test_no_match_returns_nothing(client: TestClient, db_session: Session):
    add_work(db_session, 9, [{"@type": "Isbn", "rdf:value": "0878880690"}])
    assert search_uris(client, "isbn:0000000000") == []


def test_type_filter(client: TestClient, db_session: Session):
    add_work(db_session, 10, [{"@type": "Lccn", "rdf:value": "73094113"}])
    response = client.get(
        "/search/",
        params={"q": "73094113", "scope": "identifier", "type": "instances"},
    )
    assert response.json()["total"] == 0


def test_identifier_search_uses_the_index(client: TestClient, db_session: Session):
    """The lookup must read the GIN index, not scan every row. A small test
    table makes a scan look cheap, so scans are turned off to check the index
    can serve the query at all."""
    db_session.execute(text("set local enable_seqscan = off"))
    for identifier in ["isbn:9780878880690", "9780878880690"]:
        query = select(ResourceBase.id).where(identifier_match(identifier))
        sql = query.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
        plan = "\n".join(row[0] for row in db_session.execute(text(f"explain {sql}")))
        assert IDENTIFIERS_INDEX in plan, plan


def test_html_search_has_an_identifier_scope(client: TestClient, db_session: Session):
    uri = add_work(db_session, 11, [{"@type": "Lccn", "rdf:value": "sn 85009985 "}])
    response = client.get(
        "/search", params={"q": "lccn:sn85009985", "scope": "identifier"}
    )
    assert response.status_code == 200
    assert "1 result" in response.text
    assert uri in response.text
    assert '<option value="identifier" selected>' in response.text


def test_identifier_scope_works_with_q(client: TestClient, db_session: Session):
    uri = add_work(db_session, 12, [{"@type": "Isbn", "rdf:value": "0878880690"}])
    response = client.get(
        "/search/", params={"q": "9780878880690", "scope": "identifier"}
    )
    body = response.json()
    assert [result["uri"] for result in body["results"]] == [uri]
    assert body["links"]["first"].endswith("&q=9780878880690&type=all&scope=identifier")


def test_empty_identifier_scope_returns_everything(client: TestClient):
    response = client.get("/search/", params={"q": "", "scope": "identifier"})
    assert response.status_code == 200
