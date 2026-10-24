"""
ETag / If-Match / 412 on Works and Instances (see app/utils/etag.py).
"""

import json
import pathlib
import threading
from datetime import UTC, datetime

import pytest
import rdflib
from bluecore_models.models import ResourceBase
from bluecore_models.utils.graph import CONTEXT, init_graph
from sqlalchemy import select, update

SCHEMA_NAME = rdflib.URIRef("https://schema.org/name")
CATALOGER = {"X-User": "cataloger"}


def create_work(client) -> str:
    response = client.post(
        "/works/",
        headers=CATALOGER,
        json={"data": pathlib.Path("tests/blue-core-work.jsonld").read_text()},
    )
    assert response.status_code == 201
    return response.json()["uri"].split("/")[-1]


def create_instance(client, work_id: int | None = None) -> str:
    response = client.post(
        "/instances/",
        headers=CATALOGER,
        json={
            "data": pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
            "work_id": work_id,
        },
    )
    assert response.status_code == 201
    return response.json()["uri"].split("/")[-1]


def edited(client, path: str, name: str) -> str:
    """The resource at path as JSON-LD, with a schema:name added, as an editor would save it."""
    data = client.get(f"{path}.jsonld").json()
    data["@context"] = CONTEXT
    graph = init_graph()
    graph.parse(data=json.dumps(data), format="json-ld")
    graph.add((rdflib.URIRef(data["@id"]), SCHEMA_NAME, rdflib.Literal(name)))
    return graph.serialize(format="json-ld")


def stored_name(client, path: str) -> str | None:
    data = client.get(f"{path}.jsonld").json()
    data["@context"] = CONTEXT
    graph = init_graph()
    graph.parse(data=json.dumps(data), format="json-ld")
    name = graph.value(rdflib.URIRef(data["@id"]), SCHEMA_NAME)
    return None if name is None else str(name)


@pytest.fixture
def work_path(client):
    return f"/works/{create_work(client)}"


@pytest.fixture
def instance_path(client):
    return f"/instances/{create_instance(client)}"


@pytest.fixture(params=["work", "instance"])
def resource_path(request, client):
    if request.param == "work":
        return f"/works/{create_work(client)}"
    return f"/instances/{create_instance(client)}"


# --- ETag on GET ---------------------------------------------------------------


def test_get_has_strong_etag(client, resource_path):
    etag = client.get(f"{resource_path}.jsonld").headers.get("ETag")
    assert etag is not None
    assert etag.startswith('"') and etag.endswith('"'), "strong, not W/"


def test_etag_is_the_same_for_every_serialization(client, resource_path):
    """Every RDF rendering of the one stored resource carries the same ETag."""
    etag = client.get(f"{resource_path}.jsonld").headers["ETag"]
    for suffix in [".json", ".ttl", ".nt", ".rdf", ".vnd.sinopia.json"]:
        assert client.get(f"{resource_path}{suffix}").headers.get("ETag") == etag
    for accept in ["application/ld+json", "text/turtle", "application/n-triples"]:
        response = client.get(resource_path, headers={"Accept": accept})
        assert response.headers.get("ETag") == etag


def test_etag_is_stable_between_reads(client, resource_path):
    first = client.get(f"{resource_path}.jsonld").headers["ETag"]
    assert client.get(f"{resource_path}.jsonld").headers["ETag"] == first


def test_no_etag_on_html(client, resource_path):
    assert "ETag" not in client.get(resource_path).headers
    response = client.get(resource_path, headers={"Accept": "text/html"})
    assert "ETag" not in response.headers


def test_no_etag_when_expanded(client, resource_path):
    """Expanded responses pull in other resources the ETag doesn't cover."""
    response = client.get(f"{resource_path}.jsonld?expand=true")
    assert response.status_code == 200
    assert "ETag" not in response.headers


def test_no_etag_on_cbd(client, db_session):
    work_uuid = create_work(client)
    work_id = client.get(f"/works/{work_uuid}.vnd.sinopia.json").json()["id"]
    instance_uuid = create_instance(client, work_id=work_id)

    response = client.get(f"/instances/{instance_uuid}.cbd.jsonld")
    assert response.status_code == 200
    assert "ETag" not in response.headers


# --- PUT ----------------------------------------------------------------------


def test_put_with_matching_if_match(client, resource_path):
    etag = client.get(f"{resource_path}.jsonld").headers["ETag"]

    response = client.put(
        resource_path,
        headers={**CATALOGER, "If-Match": etag},
        json={"data": edited(client, resource_path, "Matching")},
    )

    assert response.status_code == 200
    new_etag = response.headers.get("ETag")
    assert new_etag is not None and new_etag != etag
    assert client.get(f"{resource_path}.jsonld").headers["ETag"] == new_etag
    assert stored_name(client, resource_path) == "Matching"


def test_conditional_put_is_committed(client, db_session, resource_path):
    """
    A conditional save runs inside the request's own transaction (see
    session_maker_for_write), so it is only durable if the route commits it.
    Read it back on a separate connection to be sure it did.
    """
    etag = client.get(f"{resource_path}.jsonld").headers["ETag"]
    response = client.put(
        resource_path,
        headers={**CATALOGER, "If-Match": etag},
        json={"data": edited(client, resource_path, "Durable")},
    )
    assert response.status_code == 200
    uri = response.json()["uri"]

    with db_session.get_bind().connect() as other:
        data = other.execute(
            select(ResourceBase.data).where(ResourceBase.uri == uri)
        ).scalar_one()
    assert "Durable" in json.dumps(data)


def test_conditional_put_waits_for_a_concurrent_save(client, db_session, work_path):
    """
    A save that holds the row when a conditional PUT arrives makes the PUT wait,
    and once it commits the PUT is compared with what it wrote, not with what
    was there before. Here the concurrent save is played by a second connection
    that locks the row and moves updated_at, as any save of the Work would.
    """
    etag = client.get(f"{work_path}.jsonld").headers["ETag"]
    uri = client.get(f"{work_path}.vnd.sinopia.json").json()["uri"]
    body = edited(client, work_path, "Waited")
    responses = []

    with db_session.get_bind().connect() as other:
        other.execute(
            select(ResourceBase.id).where(ResourceBase.uri == uri).with_for_update()
        )

        put = threading.Thread(
            target=lambda: responses.append(
                client.put(
                    work_path,
                    headers={**CATALOGER, "If-Match": etag},
                    json={"data": body},
                )
            )
        )
        put.start()
        put.join(timeout=1)
        assert put.is_alive(), "the PUT should be waiting on the row lock"

        other.execute(
            update(ResourceBase)
            .where(ResourceBase.uri == uri)
            .values(updated_at=datetime.now(UTC))
        )
        other.commit()

    put.join(timeout=10)
    assert not put.is_alive()
    assert responses[0].status_code == 412
    assert stored_name(client, work_path) is None


def test_put_with_stale_if_match(client, resource_path):
    """Two catalogers read the same version; the second to save is refused."""
    etag = client.get(f"{resource_path}.jsonld").headers["ETag"]
    first = edited(client, resource_path, "First")
    second = edited(client, resource_path, "Second")

    response = client.put(
        resource_path, headers={**CATALOGER, "If-Match": etag}, json={"data": first}
    )
    assert response.status_code == 200
    current_etag = response.headers["ETag"]

    response = client.put(
        resource_path, headers={**CATALOGER, "If-Match": etag}, json={"data": second}
    )
    assert response.status_code == 412
    body = response.json()
    uri = client.get(f"{resource_path}.vnd.sinopia.json").json()["uri"]
    assert body["uri"] == uri
    assert body["etag"] == current_etag
    assert uri in body["detail"]
    assert response.headers["ETag"] == current_etag

    assert stored_name(client, resource_path) == "First"


def test_put_without_if_match_is_unconditional(client, resource_path):
    """Clients that don't send If-Match (Marva, sinopia_editor) still last-write-win."""
    stale = edited(client, resource_path, "Stale")
    etag = client.get(f"{resource_path}.jsonld").headers["ETag"]
    response = client.put(
        resource_path,
        headers={**CATALOGER, "If-Match": etag},
        json={"data": edited(client, resource_path, "Newer")},
    )
    assert response.status_code == 200

    response = client.put(resource_path, headers=CATALOGER, json={"data": stale})

    assert response.status_code == 200
    assert "ETag" in response.headers
    assert stored_name(client, resource_path) == "Stale"


def test_put_with_if_match_star(client, resource_path):
    response = client.put(
        resource_path,
        headers={**CATALOGER, "If-Match": "*"},
        json={"data": edited(client, resource_path, "Any")},
    )
    assert response.status_code == 200
    assert stored_name(client, resource_path) == "Any"


def test_put_with_if_match_list(client, resource_path):
    etag = client.get(f"{resource_path}.jsonld").headers["ETag"]
    response = client.put(
        resource_path,
        headers={**CATALOGER, "If-Match": f'"something-else", {etag}'},
        json={"data": edited(client, resource_path, "Listed")},
    )
    assert response.status_code == 200


@pytest.mark.parametrize("if_match", ["W/{etag}", "", '"not-the-etag"'])
def test_put_with_non_matching_if_match(client, resource_path, if_match):
    """A weak tag never passes If-Match's strong comparison, nor does a blank one."""
    etag = client.get(f"{resource_path}.jsonld").headers["ETag"]
    response = client.put(
        resource_path,
        headers={**CATALOGER, "If-Match": if_match.format(etag=etag)},
        json={"data": edited(client, resource_path, "Refused")},
    )
    assert response.status_code == 412
    assert stored_name(client, resource_path) is None


def test_put_with_if_match_on_missing_resource(client):
    """RFC 9110 13.2.1: preconditions are ignored when the answer would be a 404."""
    response = client.put(
        "/works/00000000-0000-0000-0000-000000000000",
        headers={**CATALOGER, "If-Match": "*"},
        json={"data": pathlib.Path("tests/blue-core-work.jsonld").read_text()},
    )
    assert response.status_code == 404


# --- DELETE -------------------------------------------------------------------


def test_delete_with_stale_if_match(client, resource_path):
    etag = client.get(f"{resource_path}.jsonld").headers["ETag"]
    client.put(
        resource_path,
        headers=CATALOGER,
        json={"data": edited(client, resource_path, "Changed")},
    )

    response = client.delete(resource_path, headers={**CATALOGER, "If-Match": etag})

    assert response.status_code == 412
    assert response.json()["etag"] != etag
    assert client.get(f"{resource_path}.jsonld").status_code == 200


def test_delete_with_matching_if_match(client, resource_path):
    etag = client.get(f"{resource_path}.jsonld").headers["ETag"]

    response = client.delete(resource_path, headers={**CATALOGER, "If-Match": etag})

    assert response.status_code == 204
    assert client.get(f"{resource_path}.jsonld").status_code == 404


# --- CORS ---------------------------------------------------------------------


def test_cors_exposes_etag(client, work_path):
    response = client.get(
        f"{work_path}.jsonld", headers={"Origin": "https://editor.example.org"}
    )
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    exposed = response.headers["Access-Control-Expose-Headers"].lower().split(",")
    assert "etag" in [header.strip() for header in exposed]


def test_cors_exposes_etag_on_412(client, work_path):
    response = client.put(
        work_path,
        headers={
            **CATALOGER,
            "Origin": "https://editor.example.org",
            "If-Match": '"stale"',
        },
        json={"data": edited(client, work_path, "Refused")},
    )
    assert response.status_code == 412
    assert "etag" in response.headers["Access-Control-Expose-Headers"].lower()


def test_cors_preflight_allows_if_match(client, work_path):
    response = client.options(
        work_path,
        headers={
            "Origin": "https://editor.example.org",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "if-match, content-type",
        },
    )
    assert response.status_code == 200
    allowed = response.headers["Access-Control-Allow-Headers"].lower()
    assert "if-match" in allowed
