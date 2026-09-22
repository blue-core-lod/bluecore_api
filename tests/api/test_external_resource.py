"""GET /external/resources -- the copy path.

Fetches a record from an allow-listed source and frames it the way Blue Core
frames its own, so the editor can load it for editing. Nothing is persisted:
the record becomes a Blue Core row only if the cataloger saves it.
"""

import json
import pathlib

import httpx
import pytest
from bluecore_models.models import ResourceBase, Work
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

# What a caller has. id.loc.gov publishes the http form inside its records but
# redirects browsers to https, so both turn up in the wild.
REQUESTED_URI = "https://id.loc.gov/resources/works/23118629"
WORK_URI = "http://id.loc.gov/resources/works/23118629"
INSTANCE_URI = "http://id.loc.gov/resources/instances/23118629"


@pytest.fixture
def lc_work() -> dict:
    """A real id.loc.gov work: 39 nodes of expanded JSON-LD with blank nodes."""
    with pathlib.Path("tests/loc-work-23118629.jsonld").open() as fo:
        return json.load(fo)


def test_expanded_blank_node_jsonld_comes_back_framed(
    client: TestClient, httpx_mock, lc_work
):
    """The framing is free: constructing an unsaved model runs bluecore-models'
    attribute-set event, no database involved."""
    httpx_mock.add_response(json=lc_work)

    payload = client.get("/external/resources", params={"uri": REQUESTED_URI}).json()

    # Reported as the source's own form, which is what its graph says and what
    # a derivedFrom assertion will have to match.
    assert payload["uri"] == WORK_URI
    assert payload["type"] == "works"
    assert payload["source"] == "id.loc.gov"
    data = payload["data"]
    assert data["@id"] == WORK_URI
    assert data["@type"] == ["Work", "Text", "Monograph"]
    assert data["title"][0]["mainTitle"] == ["The crying of lot 49"]
    assert data["@context"].endswith("/context.jsonld")


def test_the_jsonld_representation_is_requested_directly(
    client: TestClient, httpx_mock, lc_work
):
    """id.loc.gov 303-redirects a bare resource URI; asking for .jsonld skips
    a round trip."""
    httpx_mock.add_response(json=lc_work)

    client.get("/external/resources", params={"uri": REQUESTED_URI})

    assert str(httpx_mock.get_requests()[0].url) == f"{REQUESTED_URI}.jsonld"


def test_the_embedded_instance_is_reduced_to_a_reference(
    client: TestClient, httpx_mock, lc_work
):
    """LC's work carries its instance as a fully described, typed node.

    The editor strips the Work-Instance link when copying, so that description
    would land in unusedRDF and be merged back into the save -- where it is
    still typed and save_graph would mint an Instance nobody asked for.
    """
    httpx_mock.add_response(json=lc_work)

    data = client.get("/external/resources", params={"uri": REQUESTED_URI}).json()[
        "data"
    ]

    assert data["hasInstance"] == [{"@id": INSTANCE_URI}]


def test_nothing_is_persisted(
    client: TestClient, db_session: Session, httpx_mock, lc_work
):
    """The property the whole approach rests on: browsing is free."""
    httpx_mock.add_response(json=lc_work)
    before = db_session.scalars(select(ResourceBase.id)).all()

    client.get("/external/resources", params={"uri": REQUESTED_URI})

    assert db_session.scalars(select(ResourceBase.id)).all() == before


def test_a_record_we_already_copied_is_reported(
    client: TestClient, db_session: Session, httpx_mock, lc_work
):
    """So a client can offer to open the existing resource instead of making a
    second one derived from the same record."""
    httpx_mock.add_response(json=lc_work)
    copied_uri = "https://bcld.info/works/00000000-0000-0000-0000-000000000097"
    db_session.add(
        Work(
            id=97,
            uuid="00000000-0000-0000-0000-000000000097",
            uri=copied_uri,
            data={
                "@id": copied_uri,
                "@type": "Work",
                "title": {"@type": "Title", "mainTitle": "The crying of lot 49"},
                "adminMetadata": [
                    {"@type": "AdminMetadata", "derivedFrom": {"@id": WORK_URI}}
                ],
            },
        )
    )
    db_session.commit()

    payload = client.get("/external/resources", params={"uri": REQUESTED_URI}).json()

    assert payload["bluecore_uri"] == copied_uri


def test_an_uncopied_record_says_so_explicitly(client: TestClient, httpx_mock, lc_work):
    httpx_mock.add_response(json=lc_work)

    payload = client.get("/external/resources", params={"uri": REQUESTED_URI}).json()

    assert payload["bluecore_uri"] is None


# --- Refusals -----------------------------------------------------------------
@pytest.mark.parametrize(
    "uri",
    [
        "https://example.com/resources/works/1",
        "http://169.254.169.254/resources/works/latest",
        "http://localhost:5432/resources/works/1",
    ],
)
def test_only_configured_sources_can_be_fetched(client: TestClient, httpx_mock, uri):
    """This endpoint fetches a URL the caller supplies, so without the
    allow-list it is an open relay into whatever the container can reach."""
    response = client.get("/external/resources", params={"uri": uri})

    assert response.status_code == 400
    assert "not a configured external source" in response.json()["detail"]
    assert httpx_mock.get_requests() == []


def test_a_non_http_scheme_is_refused(client: TestClient, httpx_mock):
    response = client.get("/external/resources", params={"uri": "file:///etc/passwd"})

    assert response.status_code == 400
    assert httpx_mock.get_requests() == []


def test_an_unrecognizable_uri_is_refused(client: TestClient, httpx_mock):
    response = client.get(
        "/external/resources",
        params={"uri": "https://id.loc.gov/authorities/names/n79006936"},
    )

    assert response.status_code == 400
    assert "kind of resource" in response.json()["detail"]
    assert httpx_mock.get_requests() == []


def test_a_missing_record_is_a_404_not_a_502(client: TestClient, httpx_mock):
    httpx_mock.add_response(status_code=404)

    response = client.get("/external/resources", params={"uri": REQUESTED_URI})

    assert response.status_code == 404


def test_an_unreachable_source_is_a_504(client: TestClient, httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("nope"))

    response = client.get("/external/resources", params={"uri": REQUESTED_URI})

    assert response.status_code == 504


def test_an_unreadable_body_is_a_502(client: TestClient, httpx_mock):
    httpx_mock.add_response(content=b"<html>not json</html>")

    response = client.get("/external/resources", params={"uri": REQUESTED_URI})

    assert response.status_code == 502


def test_repeat_fetches_make_one_outbound_request(
    client: TestClient, httpx_mock, lc_work
):
    httpx_mock.add_response(json=lc_work, is_reusable=True)

    for _ in range(3):
        client.get("/external/resources", params={"uri": REQUESTED_URI})

    assert len(httpx_mock.get_requests()) == 1


def test_the_route_is_public(
    client: TestClient, keycloak_client: TestClient, httpx_mock, lc_work
):
    """Reads are public throughout the API, and this is a read. Without the
    PREFIX_PATHS entry it would 401 in production while passing every test
    that uses the `client` fixture, which bypasses the wrapper."""
    httpx_mock.add_response(json=lc_work)

    response = keycloak_client.get("/external/resources", params={"uri": REQUESTED_URI})

    assert response.status_code == 200


def test_opening_a_record_is_counted(client: TestClient, httpx_mock, lc_work):
    """Distinct records opened is the number the dump decision turns on."""
    from bluecore_api.federated import metrics

    httpx_mock.add_response(json=lc_work, is_reusable=True)

    client.get("/external/resources", params={"uri": REQUESTED_URI})
    client.get("/external/resources", params={"uri": WORK_URI})

    # The same record under both schemes is one record, not two.
    assert metrics.snapshot()["distinct_external_records_fetched"] == 1
