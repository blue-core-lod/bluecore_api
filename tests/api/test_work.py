import pathlib

import pytest
import rdflib

from bluecore_models.models import Work


def test_get_work(client, db_session):
    db_session.add(
        Work(
            id=1,
            uuid="22ba8203-4067-42ba-931e-3eb33bf4a749",
            uri="https://bcld.info/works/22ba8203-4067-42ba-931e-3eb33bf4a749",
            data=pathlib.Path("tests/blue-core-work.jsonld").read_text(),
        ),
    )
    response = client.get("/works/22ba8203-4067-42ba-931e-3eb33bf4a749")

    assert response.status_code == 200
    data = response.json()

    assert data["uri"].startswith(
        "https://bcld.info/works/22ba8203-4067-42ba-931e-3eb33bf4a749"
    )


def test_create_work(client, mocker):
    payload = {
        "data": pathlib.Path("tests/blue-core-work.jsonld").read_text(),
        "uri": "https://bcld.info/works/49413c5e-bdd5-473a-84bd-3f403c4f24d7",
    }
    create_response = client.post(
        "/works/", headers={"X-User": "cataloger"}, json=payload
    )

    assert create_response.status_code == 201
    data = create_response.json()

    assert data["data"] == payload["data"]

    # Assert timestamps exist and are identical
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] == data["updated_at"], (
        "created_at and updated_at should match on creation"
    )


def test_update_work(client, db_session, mocker):
    mocker.patch(
        "bluecore.app.main.uuid4", return_value="370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
    )
    payload = {
        "data": pathlib.Path("tests/blue-core-work.jsonld").read_text(),
        "uri": "https://bcld.info/works/370ccc0a-3280-4036-9ca1-d9b5d5daf7df",
    }
    create_response = client.post(
        "/works/", headers={"X-User": "cataloger"}, json=payload
    )

    assert create_response.status_code == 201

    work_uri = rdflib.URIRef(
        "https://bcld.info/works/370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
    )
    work_graph = rdflib.Graph()
    work_graph.parse(data=payload["data"], format="json-ld")

    work_graph.add(
        (
            work_uri,
            rdflib.URIRef("https://schema.org/name"),
            rdflib.Literal("A New Work Name"),
        )
    )
    update_response = client.put(
        "/works/370ccc0a-3280-4036-9ca1-d9b5d5daf7df",
        json={"data": work_graph.serialize(format="json-ld")},
    )

    work_graph.add(
        (
            work_uri,
            rdflib.URIRef("https://schema.org/name"),
            rdflib.Literal("A New Work Name"),
        )
    )
    update_response = client.put(
        "/works/370ccc0a-3280-4036-9ca1-d9b5d5daf7df",
        headers={"X-User": "cataloger"},
        json={"data": work_graph.serialize(format="json-ld")},
    )

    assert update_response.status_code == 200

    get_response = client.get("/works/370ccc0a-3280-4036-9ca1-d9b5d5daf7df")
    assert get_response.status_code == 200
    data = get_response.json()

    updated_work_graph = rdflib.Graph()
    updated_work_graph.parse(data=data["data"], format="json-ld")

    name = updated_work_graph.value(
        subject=work_uri,
        predicate=rdflib.URIRef("https://schema.org/name"),
    )

    assert str(name) == "A New Work Name"

    # Assert timestamps exist and are now different
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] != data["updated_at"], (
        "created_at and updated_at should not match on update"
    )
