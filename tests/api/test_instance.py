import pathlib
import pytest

import rdflib

from bluecore_models.models import Instance
from bluecore_models.utils.graph import frame_jsonld, init_graph, BF


def test_get_instance(client, db_session):
    test_instance_uuid = "75d831b9-e0d6-40f0-abb3-e9130622eb8a"
    test_instance_bluecore_uri = f"https://bcld.info/instances/{test_instance_uuid}"
    graph = rdflib.Graph().parse(
        data=pathlib.Path("tests/blue-core-work.jsonld").read_text(), format="json-ld"
    )
    data = frame_jsonld(test_instance_bluecore_uri, graph)
    db_session.add(
        Instance(
            id=2,
            uuid=test_instance_uuid,
            uri=test_instance_bluecore_uri,
            data=data,
        )
    )

    response = client.get(f"/instances/{test_instance_uuid}")
    assert response.status_code == 200
    assert response.json()["uri"].startswith(test_instance_bluecore_uri)


def test_create_instance(client):
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        format="json-ld",
    )
    payload = {
        "data": original_graph.serialize(format="json-ld"),
        "work_id": None,
    }
    response = client.post("/instances/", headers={"X-User": "cataloger"}, json=payload)
    assert response.status_code == 201
    data = response.json()
    new_graph = init_graph()
    new_graph.parse(data=data["data"], format="json-ld")

    assert len(original_graph) != len(new_graph)

    new_work_uri = rdflib.URIRef(data["uri"])
    derived_from = new_graph.value(subject=new_work_uri, predicate=BF.derivedFrom)

    assert str(derived_from).startswith(
        "https://bluecore.info/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a"
    )

    assert str(new_work_uri).startswith(
        "https://bcld.info/instances"
    ), "Minted URI uses default base url https://bcld.info/"

    # Assert timestamps exist and are identical
    assert "created_at" in data
    assert "updated_at" in data
    assert (
        data["created_at"] == data["updated_at"]
    ), "created_at and updated_at should match on creation"


def test_update_instance(client, db_session):
    instance_graph = init_graph()
    instance_graph.parse(
        data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        format="json-ld",
    )
    instance_uri = rdflib.URIRef(
        "https://bcld.info/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a"
    )
    db_session.add(
        Instance(
            id=2,
            uuid="75d831b9-e0d6-40f0-abb3-e9130622eb8a",
            uri=str(instance_uri),
            data=instance_graph.serialize(format="json-ld"),
        )
    )

    # Updates Graph
    new_oclc_number = rdflib.BNode()
    instance_graph.add((instance_uri, BF.identifiedBy, new_oclc_number))
    instance_graph.add((new_oclc_number, rdflib.RDF.type, BF.OclcNumber))
    instance_graph.add(
        (new_oclc_number, rdflib.RDF.value, rdflib.Literal("1458303129"))
    )

    put_response = client.put(
        "/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a",
        headers={"X-User": "cataloger"},
        json={"data": instance_graph.serialize(format="json-ld")},
    )
    assert put_response.status_code == 200

    # Retrieve Instance
    get_response = client.get("/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a")
    payload = get_response.json()
    new_instance_graph = init_graph()
    new_instance_graph.parse(data=payload["data"], format="json-ld")
    oclc_number = new_instance_graph.value(
        predicate=rdflib.RDF.type, object=BF.OclcNumber
    )
    oclc_number_value = new_instance_graph.value(
        subject=oclc_number, predicate=rdflib.RDF.value
    )

    assert str(oclc_number_value).startswith("1458303129")

    # Assert timestamps exist and are now different
    assert "created_at" in payload
    assert "updated_at" in payload
    assert (
        payload["created_at"] != payload["updated_at"]
    ), "created_at and updated_at should not match on update"


if __name__ == "__main__":
    pytest.main()
