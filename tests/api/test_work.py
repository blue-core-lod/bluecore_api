import json
import pathlib
import pytest
import rdflib

from bluecore_models.models import Work
from bluecore_models.utils.graph import init_graph, load_jsonld, BF


def test_get_work(client, db_session):
    # Note: since we are setting the JSON-LD data directly here on the Work model the
    # URI needs to match whats in the JSON-LD file or else the JSON-LD
    # framing will result in an empty graph.
    test_work_uuid = "370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
    test_work_bluecore_uri = f"https://api.sinopia.io/resources/{test_work_uuid}"
    jsonld_data = json.load(pathlib.Path("tests/blue-core-work.jsonld").open())
    orig_graph = load_jsonld(jsonld_data)

    db_session.add(
        Work(
            id=1,
            uuid=test_work_uuid,
            uri=test_work_bluecore_uri,
            data=jsonld_data,
        ),
    )
    response = client.get(f"/works/{test_work_uuid}")

    assert response.status_code == 200
    data = response.json()

    assert data["uri"].startswith(test_work_bluecore_uri)

    fetched_graph = load_jsonld(data["data"])
    assert len(fetched_graph) == len(orig_graph)


def test_create_work(client, mocker):
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-work.jsonld").read_text(), format="json-ld"
    )

    payload = {
        "data": original_graph.serialize(format="json-ld"),
    }
    create_response = client.post(
        "/works/", headers={"X-User": "cataloger"}, json=payload
    )

    assert create_response.status_code == 201
    data = create_response.json()
    new_graph = init_graph()

    new_graph.parse(data=data["data"], format="json-ld")

    assert len(original_graph) != len(new_graph)

    new_work_uri = rdflib.URIRef(data["uri"])
    derived_from = new_graph.value(subject=new_work_uri, predicate=BF.derivedFrom)

    assert str(derived_from).startswith(
        "https://api.sinopia.io/resources/370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
    )

    # Assert timestamps exist and are identical
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] == data["updated_at"], (
        "created_at and updated_at should match on creation"
    )


def test_update_work(client, db_session):
    payload = {
        "data": pathlib.Path("tests/blue-core-work.jsonld").read_text(),
    }
    create_response = client.post(
        "/works/", headers={"X-User": "cataloger"}, json=payload
    )

    assert create_response.status_code == 201

    work_uri = rdflib.URIRef(create_response.json()["uri"])
    work_graph = init_graph()
    data_str = json.dumps(create_response.json()["data"])
    work_graph.parse(data=data_str, format="json-ld")

    work_graph.add(
        (
            work_uri,
            rdflib.URIRef("https://schema.org/name"),
            rdflib.Literal("A New Work Name"),
        )
    )
    work_uuid = create_response.json()["uri"].split("/")[-1]
    update_response = client.put(
        f"/works/{work_uuid}",
        headers={"X-User": "cataloger"},
        json={"data": work_graph.serialize(format="json-ld")},
    )

    assert update_response.status_code == 200

    get_response = client.get(f"/works/{work_uuid}")
    assert get_response.status_code == 200
    data = get_response.json()

    updated_work_graph = init_graph()
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


if __name__ == "__main__":
    pytest.main()
