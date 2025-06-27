import json

import pytest
import rdflib

from bluecore_models.models import OtherResource
from bluecore_models.utils.graph import init_graph


@pytest.fixture
def other_graph():
    other_resource_graph = init_graph()
    unknown_uri = rdflib.URIRef("http://id.loc.gov/vocabulary/mstatus/u")
    other_resource_graph.add((unknown_uri, rdflib.RDF.type, rdflib.SKOS.Concept))
    other_resource_graph.add(
        (unknown_uri, rdflib.SKOS.prefLabel, rdflib.Literal("unknown"))
    )
    return other_resource_graph


def test_read_other_resource(client, db_session, other_graph):
    db_session.add(
        OtherResource(
            id=3,
            data=other_graph.serialize(format="json-ld"),
            uri="http://id.loc.gov/vocabulary/mstatus/u",
        )
    )
    response = client.get("/resources/3")
    assert response.status_code == 200
    assert response.json()["uri"] == "http://id.loc.gov/vocabulary/mstatus/u"


def test_create_other_resource(client, other_graph):
    create_resource_response = client.post(
        "/resources/",
        headers={"X-User": "cataloger"},
        json={"data": other_graph.serialize(format="json-ld"), "uri": None},
    )

    assert create_resource_response.status_code == 201
    other_resource_graph = init_graph()
    other_resource_graph.parse(
        data=create_resource_response.json()["data"], format="json-ld"
    )
    assert len(other_resource_graph) == len(other_graph)


def test_update_other_resource(client, db_session, other_graph):
    unknown_uri = rdflib.URIRef("http://id.loc.gov/vocabulary/mstatus/u")
    db_session.add(
        OtherResource(
            id=3,
            data=other_graph.serialize(format="json-ld"),
            uri=str(unknown_uri),
        )
    )

    other_graph.add(
        (
            unknown_uri,
            rdflib.RDFS.label,
            rdflib.Literal("Status of the resource is unknown"),
        )
    )

    update_response = client.put(
        "/resources/3",
        headers={"X-User": "cataloger"},
        json={"data": other_graph.serialize(format="json-ld")},
    )

    assert update_response.status_code == 200

    get_response = client.get("/resources/3")
    assert get_response.status_code == 200

    new_graph = init_graph()
    new_graph.parse(data=get_response.json()["data"], format="json-ld")

    label = new_graph.value(subject=unknown_uri, predicate=rdflib.RDFS.label)
    assert str(label).startswith("Status of the resource is unknown")


def test_json_other_resource(client):
    document = {"id": "abcd456efg", "label": "An Example JSON Profile"}

    create_response = client.post(
        "/resources/",
        headers={"X-User": "cataloger"},
        json={"data": json.dumps(document), "is_profile": True},
    )

    assert create_response.status_code == 201

    get_response = client.get("/resources/1")

    assert get_response.status_code == 200

    assert get_response.json()["is_profile"]

    retrieved_document = json.loads(get_response.json()["data"])

    assert document == retrieved_document


def test_read_other_resource_by_uri(client, db_session, other_graph):
    external_uri = "http://id.loc.gov/vocabulary/mstatus/u"
    db_session.add(
        OtherResource(
            id=3,
            data=other_graph.serialize(format="json-ld"),
            uri=external_uri,
        )
    )

    read_response = client.get(f"/resources/?uri={external_uri}")

    assert read_response.status_code == 200


def test_read_slice_other_resources(client, db_session):
    for i in range(11):
        db_session.add(
            OtherResource(
                id=i + 1,
                data=json.dumps({"id": i + 1, "label": f"A label for {i + 1}"}),
            )
        )

    first_slice = client.get("/resources/")
    returned_payload = first_slice.json()
    assert len(returned_payload["resources"]) == 10
    assert returned_payload["total"] == 11
    assert returned_payload["links"]["first"].endswith("?limit=10&offset=0")
    assert returned_payload["links"]["next"].endswith("?limit=10&offset=10")
    assert "prev" not in returned_payload


def test_read_slice_offset(client, db_session):
    for i in range(8):
        db_session.add(
            OtherResource(
                id=i + 1,
                data=json.dumps({"id": i + 1, "label": f"A label for {i + 1}"}),
            )
        )
    second_slice = client.get("/resources/?limit=5&offset=5")

    returned_payload = second_slice.json()
    assert len(returned_payload["resources"]) == 3
    assert returned_payload["total"] == 8
    assert returned_payload["links"]["prev"].endswith("?limit=5&offset=0")
    assert "next" not in returned_payload["links"]
    first_document = json.loads(returned_payload["resources"][0]["data"])
    assert first_document["id"] == 6
