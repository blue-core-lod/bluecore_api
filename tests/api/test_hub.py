import json
import pathlib

import pytest
import rdflib
from bluecore_models.models import BibframeOtherResources, Hub, OtherResource, Version
from bluecore_models.utils.graph import BF, CONTEXT, init_graph, load_jsonld
from bluecore_models.utils.vector_db import create_embeddings

from bluecore_api.constants import CONTEXT_URL


def test_get_hub(client, db_session):
    test_hub_uuid = "62a26d82-4e65-c696-afed-b12d215a35b1"
    test_hub_uri = f"http://id.loc.gov/resources/hubs/{test_hub_uuid}"
    jsonld_data = json.load(pathlib.Path("tests/blue-core-hub.jsonld").open())
    orig_graph = load_jsonld(jsonld_data)

    db_session.add(
        Hub(
            id=1,
            uuid=test_hub_uuid,
            uri=test_hub_uri,
            data=jsonld_data,
        )
    )

    response = client.get(
        f"/hubs/{test_hub_uuid}", headers={"Accept": "application/vnd.sinopia+json"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["uri"].startswith(test_hub_uri)
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT

    fetched_graph = load_jsonld(data["data"])
    assert len(fetched_graph) == len(orig_graph)


def test_get_expanded_hub(client, db_session):
    hub_uuid = "a1b2c3d4-0000-0000-0000-000000000001"
    hub_uri = rdflib.URIRef(f"https://bcld.info/hubs/{hub_uuid}")
    eng_uri = rdflib.URIRef("http://id.loc.gov/vocabulary/languages/eng")
    hub_graph = init_graph()
    hub_graph.add((hub_uri, rdflib.RDF.type, BF.Hub))
    hub_graph.add((hub_uri, BF.language, eng_uri))

    with pathlib.Path("tests/blue-core-other-resources.json").open() as fo:
        eng_data = json.load(fo)

    hub = Hub(
        id=1,
        uuid=hub_uuid,
        uri=str(hub_uri),
        data=json.loads(hub_graph.serialize(format="json-ld")),
    )
    db_session.add(hub)

    other_resource = OtherResource(id=2, uri=str(eng_uri), data=eng_data)
    db_session.add(other_resource)
    bf_other_resource = BibframeOtherResources(
        id=1,
        other_resource=other_resource,
        bibframe_resource=hub,
    )
    db_session.add(bf_other_resource)
    db_session.commit()

    regular_response = client.get(f"/hubs/{hub_uuid}.vnd.sinopia.json")
    data = regular_response.json()["data"]
    assert data["@context"] == CONTEXT_URL
    data["@context"] = CONTEXT

    regular_graph = load_jsonld(data)

    assert len(regular_graph) == 2

    expanded_response = client.get(f"/hubs/{hub_uuid}?expand=true")
    data = expanded_response.json()
    assert data["@context"] == CONTEXT_URL
    data["@context"] = CONTEXT
    expanded_graph = load_jsonld(data)

    assert len(expanded_graph) == 5


def test_create_hub(client, mocker, derived_from_sparql):
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-hub.jsonld").read_text(), format="json-ld"
    )

    payload = {
        "data": original_graph.serialize(format="json-ld"),
    }
    create_response = client.post(
        "/hubs/", headers={"X-User": "cataloger"}, json=payload
    )

    assert create_response.status_code == 201
    data = create_response.json()
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT
    new_graph = init_graph()
    new_graph.parse(data=data["data"], format="json-ld")

    assert len(original_graph) != len(new_graph)

    results = new_graph.query(derived_from_sparql)
    derived_from = results.bindings[0]["derived_from"]

    assert str(derived_from).startswith(
        "http://id.loc.gov/resources/hubs/62a26d82-4e65-c696-afed-b12d215a35b1"
    )

    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] == data["updated_at"], (
        "created_at and updated_at should match on creation"
    )


def test_update_hub(client, db_session):
    payload = {
        "data": pathlib.Path("tests/blue-core-hub.jsonld").read_text(),
    }
    create_response = client.post(
        "/hubs/", headers={"X-User": "cataloger"}, json=payload
    )

    assert create_response.status_code == 201

    data = create_response.json()
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT
    hub_uri = rdflib.URIRef(data["uri"])
    hub_graph = init_graph()
    data_str = json.dumps(data["data"])
    hub_graph.parse(data=data_str, format="json-ld")

    hub_graph.add(
        (
            hub_uri,
            rdflib.URIRef("https://schema.org/name"),
            rdflib.Literal("An Updated Hub Name"),
        )
    )
    hub_uuid = create_response.json()["uri"].split("/")[-1]
    update_response = client.put(
        f"/hubs/{hub_uuid}",
        headers={"X-User": "cataloger"},
        json={"data": hub_graph.serialize(format="json-ld")},
    )

    assert update_response.status_code == 200

    get_response = client.get(f"/hubs/{hub_uuid}.vnd.sinopia.json")
    assert get_response.status_code == 200
    data = get_response.json()
    data["data"]["@context"] = CONTEXT

    updated_hub_graph = init_graph()
    updated_hub_graph.parse(data=data["data"], format="json-ld")

    name = updated_hub_graph.value(
        subject=hub_uri,
        predicate=rdflib.URIRef("https://schema.org/name"),
    )

    assert str(name) == "An Updated Hub Name"

    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] != data["updated_at"], (
        "created_at and updated_at should not match on update"
    )


def test_create_hub_jsonld(client, mocker, derived_from_sparql):
    """A raw JSON-LD body (application/ld+json) is accepted in addition to the
    Sinopia-specific body."""
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-hub.jsonld").read_text(), format="json-ld"
    )

    create_response = client.post(
        "/hubs/",
        headers={"X-User": "cataloger", "Content-Type": "application/ld+json"},
        content=original_graph.serialize(format="json-ld"),
    )

    assert create_response.status_code == 201
    data = create_response.json()
    assert data["data"]["@context"] == CONTEXT_URL
    assert data["uri"].startswith("https://bcld.info/hubs")


def test_update_hub_jsonld(client, db_session):
    create_response = client.post(
        "/hubs/",
        headers={"X-User": "cataloger"},
        json={"data": pathlib.Path("tests/blue-core-hub.jsonld").read_text()},
    )
    assert create_response.status_code == 201

    data = create_response.json()
    data["data"]["@context"] = CONTEXT
    hub_uri = rdflib.URIRef(data["uri"])
    hub_graph = init_graph()
    hub_graph.parse(data=json.dumps(data["data"]), format="json-ld")
    hub_graph.add(
        (
            hub_uri,
            rdflib.URIRef("https://schema.org/name"),
            rdflib.Literal("A JSON-LD Hub Name"),
        )
    )
    hub_uuid = data["uri"].split("/")[-1]

    update_response = client.put(
        f"/hubs/{hub_uuid}",
        headers={"X-User": "cataloger", "Content-Type": "application/ld+json"},
        content=hub_graph.serialize(format="json-ld"),
    )
    assert update_response.status_code == 200

    get_response = client.get(f"/hubs/{hub_uuid}.vnd.sinopia.json")
    data = get_response.json()
    data["data"]["@context"] = CONTEXT
    updated_hub_graph = init_graph()
    updated_hub_graph.parse(data=data["data"], format="json-ld")
    name = updated_hub_graph.value(
        subject=hub_uri, predicate=rdflib.URIRef("https://schema.org/name")
    )
    assert str(name) == "A JSON-LD Hub Name"


def test_get_hub_embedding(client, db_session, vector_client):
    sample_hub_graph = init_graph()
    sample_hub_uuid = "a1b2c3d4-0000-0000-0000-000000000002"
    sample_hub_uri = rdflib.URIRef(f"https://bcld.info/hubs/{sample_hub_uuid}")
    sample_hub_graph.add((sample_hub_uri, rdflib.RDF.type, BF.Hub))
    sample_hub_graph.add(
        (sample_hub_uri, rdflib.RDFS.label, rdflib.Literal("A Sample Hub", lang="en"))
    )
    db_session.add(
        Hub(
            id=3,
            uuid=sample_hub_uuid,
            uri=str(sample_hub_uri),
            data=json.loads(sample_hub_graph.serialize(format="json-ld")),
        )
    )

    version = db_session.query(Version).where(Version.resource_id == 3).first()
    create_embeddings(version, "hubs", vector_client)

    get_response = client.get(f"/hubs/{sample_hub_uuid}/embeddings")
    payload = get_response.json()

    assert len(payload["embedding"]) == len(sample_hub_graph)


def test_new_hub_embedding(client, db_session, vector_client):
    sample_hub_graph = init_graph()
    sample_hub_uuid = "a1b2c3d4-0000-0000-0000-000000000003"
    sample_hub_uri = rdflib.URIRef(f"https://bcld.info/hubs/{sample_hub_uuid}")
    sample_hub_graph.add((sample_hub_uri, rdflib.RDF.type, BF.Hub))
    title_bnode = rdflib.BNode()
    sample_hub_graph.add((sample_hub_uri, BF.title, title_bnode))
    sample_hub_graph.add(
        (title_bnode, BF.mainTitle, rdflib.Literal("A Great Hub", lang="en"))
    )
    db_session.add(
        Hub(
            id=4,
            uuid=sample_hub_uuid,
            uri=str(sample_hub_uri),
            data=json.loads(sample_hub_graph.serialize(format="json-ld")),
        )
    )
    post_result = client.post(
        f"/hubs/{sample_hub_uuid}/embeddings", headers={"X-User": "cataloger"}
    )
    payload = post_result.json()
    assert len(payload["embedding"]) == len(sample_hub_graph)


if __name__ == "__main__":
    pytest.main()
