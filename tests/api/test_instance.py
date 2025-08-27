import json
import pathlib

import pytest
import rdflib
from bluecore_models.models import Instance, Version
from bluecore_models.utils.graph import BF, init_graph, load_jsonld
from bluecore_models.utils.vector_db import create_embeddings


def test_get_instance(client, db_session):
    test_instance_uuid = "75d831b9-e0d6-40f0-abb3-e9130622eb8a"
    test_instance_bluecore_uri = f"https://bluecore.info/instances/{test_instance_uuid}"
    jsonld_data = json.load(pathlib.Path("tests/blue-core-instance.jsonld").open())
    orig_graph = load_jsonld(jsonld_data)

    db_session.add(
        Instance(
            id=2,
            uuid=test_instance_uuid,
            uri=test_instance_bluecore_uri,
            data=jsonld_data,
        )
    )

    response = client.get(f"/instances/{test_instance_uuid}")
    assert response.status_code == 200

    assert response.json()["uri"].startswith(test_instance_bluecore_uri)

    fetched_graph = load_jsonld(response.json()["data"])
    assert len(orig_graph) == len(fetched_graph), "graph lengths are the same"


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

    assert str(new_work_uri).startswith("https://bcld.info/instances"), (
        "Minted URI uses default base url https://bcld.info/"
    )

    # Assert timestamps exist and are identical
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] == data["updated_at"], (
        "created_at and updated_at should match on creation"
    )


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
            data=json.loads(instance_graph.serialize(format="json-ld")),
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
    assert payload["created_at"] != payload["updated_at"], (
        "created_at and updated_at should not match on update"
    )


def test_get_instance_embeddings(client, db_session, vector_client):
    sample_instance_graph = init_graph()
    instance_uuid = "3890cc27-6fbf-42b6-8efb-d0ed40e9188e"
    instance_uri = rdflib.URIRef(f"https://bcld.info/instances/{instance_uuid}")
    sample_instance_graph.add((instance_uri, rdflib.RDF.type, BF.Instance))
    title_uri = rdflib.URIRef(f"https://bcld.info/instances/{instance_uuid}#abdef345")
    sample_instance_graph.add((instance_uri, BF.title, title_uri))
    sample_instance_graph.add(
        (title_uri, BF.mainTitle, rdflib.Literal("A Fine Instance", lang="en"))
    )
    db_session.add(
        Instance(
            id=3,
            uuid=instance_uuid,
            uri=str(instance_uri),
            data=json.loads(sample_instance_graph.serialize(format="json-ld")),
        )
    )
    version = db_session.query(Version).where(Version.resource_id == 3).first()
    create_embeddings(version, "instances", vector_client)

    # Query client for embeddings
    get_response = client.get(f"/instances/{instance_uuid}/embeddings")
    payload = get_response.json()

    assert len(payload["embedding"]) == 3
    # Sorting embeddings because Milvus doesn't ensure insert order
    sorted_embedding = sorted(payload["embedding"], key=lambda x: x["text"])
    assert len(sorted_embedding[0]["vector"]) == 768
    assert sorted_embedding[2]["text"].startswith(
        "<https://bcld.info/instances/3890cc27-6fbf-42b6-8efb-d0ed40e9188e> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://id.loc.gov/ontologies/bibframe/Instance>"
    )


def test_new_instance_embedding(client, db_session, vector_client):
    sample_graph = init_graph()
    uuid = "75d831b9-e0d6-40f0-abb3-e9130622eb8a"
    uri = rdflib.URIRef(
        "https://bluecore.info/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a"
    )
    sample_graph.add((uri, rdflib.RDF.type, BF.Instance))
    sample_graph.add((uri, rdflib.RDFS.label, rdflib.Literal("Another Instance")))

    db_session.add(
        Instance(
            id=4,
            uuid=uuid,
            uri=str(uri),
            data=json.loads(sample_graph.serialize(format="json-ld")),
        )
    )
    post_result = client.post(
        f"/instances/{uuid}/embeddings", headers={"X-User": "cataloger"}
    )

    payload = post_result.json()
    assert payload["instance_uri"] == str(uri)
    assert len(payload["embedding"]) == len(sample_graph)
    assert len(payload["embedding"][0]["vector"]) == 768


if __name__ == "__main__":
    pytest.main()
