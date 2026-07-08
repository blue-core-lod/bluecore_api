import json
import pathlib
from typing import Any

import pytest
import rdflib
from bluecore_models.models import (
    BibframeOtherResources,
    Instance,
    OtherResource,
    Version,
)
from bluecore_models.utils.graph import BF, CONTEXT, init_graph, load_jsonld
from bluecore_models.utils.vector_db import create_embeddings

from bluecore_api.app.utils.serialize.response_generator import CONTEXT_URL

test_instance_uuid = "75d831b9-e0d6-40f0-abb3-e9130622eb8a"
test_instance_bluecore_uri = f"https://bluecore.info/instances/{test_instance_uuid}"
jsonld_data = json.load(pathlib.Path("tests/blue-core-instance.jsonld").open())
orig_graph = load_jsonld(jsonld_data)

test_expanded_instance_uuid = "1e09c839-474d-4ab5-8b44-479e08927045"
test_expanded_instance_uri = rdflib.URIRef(
    f"https://bcld.info/instances/{test_instance_uuid}"
)
kor_uri = rdflib.URIRef("http://id.loc.gov/vocabulary/languages/kor")
test_expanded_instance_graph = init_graph()
test_expanded_instance_graph.add(
    (test_expanded_instance_uri, rdflib.RDF.type, BF.Instance)
)
test_expanded_instance_graph.add((test_expanded_instance_uri, BF.language, kor_uri))
with pathlib.Path("tests/blue-core-other-resources2.json").open() as fo:
    kor_data = json.load(fo)


def add_test_instance(db_session):
    db_session.add(
        Instance(
            id=1,
            uuid=test_instance_uuid,
            uri=str(test_instance_bluecore_uri),
            data=json.loads(orig_graph.serialize(format="json-ld")),
        )
    )
    db_session.commit()


def add_test_expanded_instance(db_session):
    instance = Instance(
        id=1,
        uuid=test_expanded_instance_uuid,
        uri=str(test_expanded_instance_uri),
        data=json.loads(test_expanded_instance_graph.serialize(format="json-ld")),
    )

    db_session.add(instance)
    other_resource = OtherResource(id=2, uri=str(kor_uri), data=kor_data)
    db_session.add(other_resource)
    bf_other_resource = BibframeOtherResources(
        id=1, other_resource=other_resource, bibframe_resource=instance
    )
    db_session.add(bf_other_resource)
    db_session.commit()


def test_get_instance_sinopia_json(client, db_session):
    add_test_instance(db_session)

    response = client.get(f"/instances/{test_instance_uuid}.vnd.sinopia.json")
    assert response.status_code == 200

    assert response.json()["uri"].startswith(test_instance_bluecore_uri)

    assert response.json()["data"]["@context"] == CONTEXT_URL
    data = response.json()["data"]
    data["@context"] = CONTEXT
    fetched_graph = load_jsonld(data)
    assert len(orig_graph) == len(fetched_graph), "graph lengths are the same"


def test_get_expanded_instance_sinopia_json(client, db_session):
    add_test_expanded_instance(db_session)

    # Regular Get Call for Instance and application/vnd.sinopia+json format
    regular_instance_result = client.get(
        f"/instances/{test_expanded_instance_uuid}",
        headers={"Accept": "application/vnd.sinopia+json"},
    )
    assert regular_instance_result.json()["data"]["@context"] == CONTEXT_URL
    data: dict[str, Any] = regular_instance_result.json()["data"]
    data["@context"] = CONTEXT
    regular_instance_graph = load_jsonld(data)

    assert len(regular_instance_graph) == 2

    # Test GET with expand = True
    expanded_instance_result = client.get(
        f"/instances/{test_expanded_instance_uuid}?expand=true",
        headers={"Accept": "application/vnd.sinopia+json"},
    )
    data = expanded_instance_result.json()["data"]
    data["@context"] = CONTEXT
    expanded_instance_graph = load_jsonld(data)

    assert len(expanded_instance_graph) == 5

    # Test GET with expand = False and .vnd.sinopia.json format
    expand_false_result = client.get(
        f"/instances/{test_expanded_instance_uuid}.vnd.sinopia.json?expand=false",
    )
    data = expand_false_result.json()["data"]
    data["@context"] = CONTEXT
    expand_false_graph = load_jsonld(data)

    assert len(expand_false_graph) == len(regular_instance_graph)


def test_get_instance_jsonld(client, db_session):
    add_test_instance(db_session)

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    assert response.json()["@id"] == test_instance_bluecore_uri

    response = client.get(f"/instances/{test_instance_uuid}.jsonld")
    assert response.status_code == 200
    assert response.json()["@id"] == test_instance_bluecore_uri
    assert response.json()["@context"] == CONTEXT_URL


def test_get_instance_json(client, db_session):
    add_test_instance(db_session)

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "application/json"}
    )
    assert response.status_code == 200
    assert response.json()["@id"] == test_instance_bluecore_uri

    response = client.get(f"/instances/{test_instance_uuid}.json")
    assert response.status_code == 200
    assert response.json()["@id"] == test_instance_bluecore_uri
    assert response.json()["@context"] == CONTEXT_URL


def test_get_instance_rdf_xml(client, db_session):
    add_test_instance(db_session)

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "application/rdf+xml"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/rdf+xml")

    response = client.get(f"/instances/{test_instance_uuid}.rdf")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/rdf+xml")


def test_get_instance_ntriples(client, db_session):
    add_test_instance(db_session)

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "application/n-triples"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/n-triples")

    response = client.get(f"/instances/{test_instance_uuid}.nt")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/n-triples")


def test_get_instance_turtle(client, db_session):
    add_test_instance(db_session)

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "text/turtle"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/turtle")

    response = client.get(f"/instances/{test_instance_uuid}.ttl")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/turtle")


def test_get_instance_html(client, db_session):
    add_test_instance(db_session)

    # Only a browser (Accept: text/html) on the clean URL gets the HTML view.
    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "text/html"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert "BIBFRAME Instance" in response.text
    # The view links to the alternative RDF serializations.
    assert f"{test_instance_bluecore_uri}.ttl" in response.text

    # An unrecognized format (e.g. `.html`, `.xml`) falls through to the default
    # serialization, which is the HTML view.
    response = client.get(f"/instances/{test_instance_uuid}.html")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")


# cbd requires work & instance and will be tested in test_cbd.py


def test_create_instance(client, derived_from_sparql):
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
    data: dict[str, Any] = response.json()
    new_graph = init_graph()
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT
    new_graph.parse(data=data["data"], format="json-ld")

    assert len(original_graph) != len(new_graph)

    results = new_graph.query(derived_from_sparql)
    derived_from = results.bindings[0]["derived_from"]

    assert str(derived_from).startswith(
        "https://bluecore.info/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a"
    )

    assert data["uri"].startswith("https://bcld.info/instances"), (
        "Minted URI uses default base url https://bcld.info/"
    )

    # Assert timestamps exist and are identical
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] == data["updated_at"], (
        "created_at and updated_at should match on creation"
    )


def test_create_instance_without_work_id(client, derived_from_sparql):
    """The editor omits work_id entirely when saving a standalone instance;
    work_id is optional, so this must not 422."""
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        format="json-ld",
    )
    # Note: no "work_id" key at all.
    payload = {"data": original_graph.serialize(format="json-ld")}
    response = client.post("/instances/", headers={"X-User": "cataloger"}, json=payload)
    assert response.status_code == 201


def test_create_instance_with_readonly(client, derived_from_sparql):
    """If a user has both create and cataloger-read-only roles, the read-only role takes precedence and they cannot create an instance."""
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        format="json-ld",
    )
    # Note: no "work_id" key at all.
    payload = {"data": original_graph.serialize(format="json-ld")}
    response = client.post(
        "/instances/", headers={"X-User": "cataloger-conflicting"}, json=payload
    )
    assert response.status_code == 403


def test_update_instance(client, db_session):
    create_response = client.post(
        "/instances/",
        headers={"X-User": "cataloger"},
        json={
            "data": pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
            "work_id": None,
        },
    )
    assert create_response.status_code == 201
    data = create_response.json()
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT

    instance_uri = rdflib.URIRef(data["uri"])
    instance_uuid = data["uri"].split("/")[-1]
    instance_graph = init_graph()
    instance_graph.parse(data=json.dumps(data["data"]), format="json-ld")

    # Updates Graph
    new_oclc_number = rdflib.BNode()
    instance_graph.add((instance_uri, BF.identifiedBy, new_oclc_number))
    instance_graph.add((new_oclc_number, rdflib.RDF.type, BF.OclcNumber))
    instance_graph.add(
        (new_oclc_number, rdflib.RDF.value, rdflib.Literal("1458303129"))
    )

    put_response = client.put(
        f"/instances/{instance_uuid}",
        headers={"X-User": "cataloger"},
        json={"data": instance_graph.serialize(format="json-ld")},
    )
    assert put_response.status_code == 200
    assert put_response.json()["data"]["@context"] == CONTEXT_URL

    # Retrieve Instance
    get_response = client.get(f"/instances/{instance_uuid}.vnd.sinopia.json")
    payload = get_response.json()
    assert payload["data"]["@context"] == CONTEXT_URL
    payload["data"]["@context"] = CONTEXT
    new_instance_graph = init_graph()
    new_instance_graph.parse(data=json.dumps(payload["data"]), format="json-ld")
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


def test_create_instance_jsonld(client, derived_from_sparql):
    """A raw JSON-LD body (application/ld+json) is accepted in addition to the
    Sinopia-specific body."""
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        format="json-ld",
    )

    response = client.post(
        "/instances/",
        headers={"X-User": "cataloger", "Content-Type": "application/ld+json"},
        content=original_graph.serialize(format="json-ld"),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["data"]["@context"] == CONTEXT_URL
    assert data["uri"].startswith("https://bcld.info/instances")


def test_update_instance_jsonld(client, db_session):
    create_response = client.post(
        "/instances/",
        headers={"X-User": "cataloger"},
        json={"data": pathlib.Path("tests/blue-core-instance.jsonld").read_text()},
    )
    assert create_response.status_code == 201
    data = create_response.json()
    data["data"]["@context"] = CONTEXT

    instance_uri = rdflib.URIRef(data["uri"])
    instance_uuid = data["uri"].split("/")[-1]
    instance_graph = init_graph()
    instance_graph.parse(data=json.dumps(data["data"]), format="json-ld")
    instance_graph.add(
        (
            instance_uri,
            rdflib.URIRef("https://schema.org/name"),
            rdflib.Literal("A JSON-LD Instance Name"),
        )
    )

    put_response = client.put(
        f"/instances/{instance_uuid}",
        headers={"X-User": "cataloger", "Content-Type": "application/ld+json"},
        content=instance_graph.serialize(format="json-ld"),
    )
    assert put_response.status_code == 200

    get_response = client.get(f"/instances/{instance_uuid}.vnd.sinopia.json")
    payload = get_response.json()
    payload["data"]["@context"] = CONTEXT
    new_instance_graph = init_graph()
    new_instance_graph.parse(data=json.dumps(payload["data"]), format="json-ld")
    name = new_instance_graph.value(
        subject=instance_uri, predicate=rdflib.URIRef("https://schema.org/name")
    )
    assert str(name) == "A JSON-LD Instance Name"


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
