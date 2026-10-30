import json

import bibframe_json
import pytest
from bluecore_models.models import Instance, Work
from bluecore_models.namespaces import BF
from fastapi.testclient import TestClient
from rdflib import RDF, Graph, URIRef
from sqlalchemy.orm import Session

HEADERS = {"X-User": "cataloger"}


def _lc_cbd() -> Graph:
    """A real LC CBD: two Instances of one Work."""
    graph = Graph()
    graph.parse("tests/23807141.jsonld")
    return graph


def _instances(graph: Graph) -> list[str]:
    return sorted(
        str(s) for s in graph.subjects(RDF.type, BF.Instance) if isinstance(s, URIRef)
    )


# The serializations a client might send, as rdflib writes them. JSON-LD is
# expanded, with no @context, as id.loc.gov serves it.
SERIALIZATIONS = [
    ("application/ld+json", "json-ld"),
    ("application/rdf+xml", "xml"),
    ("text/turtle", "turtle"),
]


@pytest.mark.parametrize("media_type,rdflib_format", SERIALIZATIONS)
@pytest.mark.parametrize("which", [0, 1])
def test_frames_each_serialization_as_a_bounded_description(
    client: TestClient, media_type: str, rdflib_format: str, which: int
):
    """
    Either Instance in LC's CBD: one says instanceOf, and the other is named
    only by the Work's hasInstance.
    """
    graph = _lc_cbd()
    instance = _instances(graph)[which]
    resp = client.post(
        "/frame",
        params={"instance": instance},
        headers={**HEADERS, "Content-Type": media_type},
        content=graph.serialize(format=rdflib_format),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/ld+json")
    document = resp.json()
    assert (
        bibframe_json.validate(document, ontology=False, kind=bibframe_json.BOUNDED)
        == []
    )
    assert document["@context"] == bibframe_json.CONTEXT_URL
    assert document["@id"] == instance
    [work] = document["instanceOf"]
    assert (URIRef(work["@id"]), BF.hasInstance, URIRef(instance)) in graph or (
        URIRef(instance),
        BF.instanceOf,
        URIRef(work["@id"]),
    ) in graph


def test_reads_a_multipart_file(client: TestClient):
    graph = _lc_cbd()
    instance = _instances(graph)[0]
    resp = client.post(
        "/frame",
        params={"instance": instance},
        headers=HEADERS,
        files={"file": ("cbd.ttl", graph.serialize(format="turtle"), "text/turtle")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["@id"] == instance


def test_saves_nothing(client: TestClient, db_session: Session):
    graph = _lc_cbd()
    client.post(
        "/frame",
        params={"instance": _instances(graph)[0]},
        headers={**HEADERS, "Content-Type": "text/turtle"},
        content=graph.serialize(format="turtle"),
    )
    assert db_session.query(Instance).count() == 0
    assert db_session.query(Work).count() == 0


TWO_RESOURCES = """
@prefix bf: <http://id.loc.gov/ontologies/bibframe/> .
<http://example.org/instances/1> a bf:Instance, bf:Print ;
    bf:instanceOf <http://example.org/works/1> .
<http://example.org/works/1> a bf:Work, bf:Text ;
    bf:language <http://id.loc.gov/vocabulary/languages/eng> .
"""


def _post_turtle(client: TestClient, turtle: str, **params: str):
    return client.post(
        "/frame",
        params=params,
        headers={**HEADERS, "Content-Type": "text/turtle"},
        content=turtle.encode(),
    )


def test_finds_the_only_instance_without_being_told(client: TestClient):
    resp = _post_turtle(client, TWO_RESOURCES)
    assert resp.status_code == 200, resp.text
    assert resp.json()["@id"] == "http://example.org/instances/1"


def test_asks_which_instance_when_there_are_several(client: TestClient):
    graph = _lc_cbd()
    resp = client.post(
        "/frame",
        headers={**HEADERS, "Content-Type": "text/turtle"},
        content=graph.serialize(format="turtle"),
    )
    assert resp.status_code == 422
    assert "?instance=" in resp.json()["detail"]


def test_refuses_an_instance_the_graph_does_not_describe(client: TestClient):
    resp = _post_turtle(client, TWO_RESOURCES, instance="http://example.org/other")
    assert resp.status_code == 422


def test_refuses_an_instance_with_no_work(client: TestClient):
    resp = _post_turtle(
        client,
        "<http://example.org/i> a <http://id.loc.gov/ontologies/bibframe/Instance> .",
    )
    assert resp.status_code == 422
    assert "instanceOf" in resp.json()["detail"]


def test_refuses_a_media_type_it_does_not_read(client: TestClient):
    resp = client.post(
        "/frame",
        headers={**HEADERS, "Content-Type": "application/n-triples"},
        content=b"<a:b> <a:c> <a:d> .",
    )
    assert resp.status_code == 415


@pytest.mark.parametrize(
    "media_type,body",
    [
        ("text/turtle", b"this is not turtle"),
        ("application/rdf+xml", b"<rdf:RDF"),
        ("application/ld+json", b"{not json"),
        # An inline context could reach the network, so it isn't read.
        (
            "application/ld+json",
            json.dumps({"@context": {"@vocab": "http://example.org/"}}).encode(),
        ),
    ],
)
def test_refuses_what_it_cannot_read(client: TestClient, media_type: str, body: bytes):
    resp = client.post(
        "/frame", headers={**HEADERS, "Content-Type": media_type}, content=body
    )
    assert resp.status_code == 422


def test_does_not_read_external_entities(client: TestClient, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("the secret")
    body = f"""<?xml version="1.0"?>
<!DOCTYPE rdf:RDF [<!ENTITY secret SYSTEM "file://{secret}">]>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:bf="http://id.loc.gov/ontologies/bibframe/">
  <bf:Instance rdf:about="http://example.org/instances/1">
    <bf:instanceOf>
      <bf:Work rdf:about="http://example.org/works/1">
        <bf:note>&secret;</bf:note>
      </bf:Work>
    </bf:instanceOf>
  </bf:Instance>
</rdf:RDF>"""
    resp = client.post(
        "/frame",
        headers={**HEADERS, "Content-Type": "application/rdf+xml"},
        content=body.encode(),
    )
    assert "the secret" not in resp.text
