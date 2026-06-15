import json
import pathlib

import pytest
import rdflib
from bluecore_models.models import BibframeOtherResources, OtherResource, Version, Work
from bluecore_models.utils.graph import BF, init_graph, load_jsonld
from bluecore_models.utils.vector_db import create_embeddings

test_work_uuid = "370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
test_work_bluecore_uri = f"https://api.sinopia.io/resources/{test_work_uuid}"
jsonld_data = json.load(pathlib.Path("tests/blue-core-work.jsonld").open())
orig_graph = load_jsonld(jsonld_data)

expanded_work_uuid = "7b7ed475-9126-4368-925a-8b8c5520250e"
expanded_work_uri = rdflib.URIRef(f"https://bcld.info/works/{expanded_work_uuid}")
eng_uri = rdflib.URIRef("http://id.loc.gov/vocabulary/languages/eng")
expanded_work_graph = init_graph()
expanded_work_graph.add((expanded_work_uri, rdflib.RDF.type, BF.Work))
expanded_work_graph.add((expanded_work_uri, BF.language, eng_uri))
with pathlib.Path("tests/blue-core-other-resources.json").open() as fo:
    eng_data = json.load(fo)


def add_test_work(db_session):
    db_session.add(
        Work(
            id=1,
            uuid=test_work_uuid,
            uri=test_work_bluecore_uri,
            data=jsonld_data,
        ),
    )
    db_session.commit()


def add_test_expanded_work(db_session):
    work = Work(
        id=1,
        uuid=expanded_work_uuid,
        uri=str(expanded_work_uri),
        data=json.loads(expanded_work_graph.serialize(format="json-ld")),
    )
    db_session.add(work)

    other_resource = OtherResource(id=2, uri=str(eng_uri), data=eng_data)
    db_session.add(other_resource)
    bf_other_resource = BibframeOtherResources(
        id=1,
        other_resource=other_resource,
        bibframe_resource=work,
    )
    db_session.add(bf_other_resource)
    db_session.commit()


def test_get_work_vnd_sinopia_json(client, db_session):
    # Note: since we are setting the JSON-LD data directly here on the Work model the
    # URI needs to match whats in the JSON-LD file or else the JSON-LD
    # framing will result in an empty graph.
    add_test_work(db_session)

    response = client.get(
        f"/works/{test_work_uuid}", headers={"Accept": "application/vnd.sinopia+json"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["uri"].startswith(test_work_bluecore_uri)

    fetched_graph = load_jsonld(data["data"])
    assert len(fetched_graph) == len(orig_graph)


def test_get_expanded_work(client, db_session):
    add_test_expanded_work(db_session)

    # Test regular GET response without expand parameter
    regular_work_response = client.get(f"/works/{expanded_work_uuid}.vnd.sinopia.json")
    regular_work_graph = load_jsonld(regular_work_response.json()["data"])

    assert len(regular_work_graph) == 2

    # Test GET with expand = True
    expanded_work_response = client.get(
        f"/works/{expanded_work_uuid}?expand=true",
        headers={"Accept": "application/vnd.sinopia+json"},
    )
    expanded_work_graph = load_jsonld(expanded_work_response.json()["data"])

    assert len(expanded_work_graph) == 5


def test_get_work_jsonld(client, db_session):
    add_test_work(db_session)

    response = client.get(
        f"/works/{test_work_uuid}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    assert response.json()["@id"] == test_work_bluecore_uri

    response = client.get(f"/works/{test_work_uuid}.jsonld")
    assert response.status_code == 200
    assert response.json()["@id"] == test_work_bluecore_uri


def test_get_work_rdf_xml(client, db_session):
    add_test_work(db_session)

    response = client.get(
        f"/works/{test_work_uuid}", headers={"Accept": "application/rdf+xml"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/rdf+xml")

    response = client.get(f"/works/{test_work_uuid}.rdf")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/rdf+xml")


def test_get_work_ntriples(client, db_session):
    add_test_work(db_session)

    response = client.get(
        f"/works/{test_work_uuid}", headers={"Accept": "application/n-triples"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/n-triples")

    response = client.get(f"/works/{test_work_uuid}.nt")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/n-triples")


def test_get_work_turtle(client, db_session):
    add_test_work(db_session)

    response = client.get(f"/works/{test_work_uuid}", headers={"Accept": "text/turtle"})
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/turtle")

    response = client.get(f"/works/{test_work_uuid}.ttl")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/turtle")


# cbd requires work & instance and will be tested in test_cbd.py


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

    get_response = client.get(f"/works/{work_uuid}.vnd.sinopia.json")
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


def test_get_work_embedding(client, db_session, vector_client):
    sample_work_graph = init_graph()
    sample_work_uuid = "55ce1584-9a98-4063-84c9-775c53623142"
    sample_work_uri = rdflib.URIRef(f"https://bcld.info/works/{sample_work_uuid}")
    sample_work_graph.add((sample_work_uri, rdflib.RDF.type, BF.Work))
    sample_work_graph.add(
        (sample_work_uri, rdflib.RDFS.label, rdflib.Literal("A Sample Work", lang="en"))
    )
    db_session.add(
        Work(
            id=3,
            uuid=sample_work_uuid,
            uri=str(sample_work_uri),
            data=json.loads(sample_work_graph.serialize(format="json-ld")),
        )
    )

    version = db_session.query(Version).where(Version.resource_id == 3).first()
    create_embeddings(version, "works", vector_client)

    get_response = client.get(f"/works/{sample_work_uuid}/embeddings")
    payload = get_response.json()

    assert len(payload["embedding"]) == len(sample_work_graph)


def test_new_work_embedding(client, db_session, vector_client):
    sample_work_graph = init_graph()
    sample_work_uuid = "a32ccd94-0c4f-415f-ba05-432ea4176f4e"
    sample_work_uri = rdflib.URIRef(f"https://bcld.info/works/{sample_work_uuid}")
    sample_work_graph.add((sample_work_uri, rdflib.RDF.type, BF.Work))
    title_bnode = rdflib.BNode()
    sample_work_graph.add((sample_work_uri, BF.title, title_bnode))
    sample_work_graph.add(
        (title_bnode, BF.mainTitle, rdflib.Literal("A Great Work", lang="en"))
    )
    db_session.add(
        Work(
            id=4,
            uuid=sample_work_uuid,
            uri=str(sample_work_uri),
            data=json.loads(sample_work_graph.serialize(format="json-ld")),
        )
    )
    post_result = client.post(
        f"/works/{sample_work_uuid}/embeddings", headers={"X-User": "cataloger"}
    )
    payload = post_result.json()
    assert len(payload["embedding"]) == len(sample_work_graph)


if __name__ == "__main__":
    pytest.main()
