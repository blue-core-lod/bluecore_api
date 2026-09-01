import pathlib
import xml.etree.ElementTree as ET
from typing import Any

import pytest
from bluecore_models.bluecore_graph import BluecoreGraph
from bluecore_models.models import Instance, Work
from bluecore_models.namespaces import BF
from bluecore_models.utils.graph import init_graph
from fastapi.testclient import TestClient
from lxml import etree
from rdflib import RDF, Graph, URIRef
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluecore_api.app.utils.serialize.cbd import (
    XPATH_NAMESPACES,
    generate_cbd_graph,
    generate_cbd_xml,
    related_works,
    reorder_instance_types,
    reorder_work_types,
)
from bluecore_api.constants import BibframeType


def add_work(client: TestClient, db_session: Session) -> Work | None:
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/cbd-work.jsonld").read_text(), format="json-ld"
    )
    payload = {
        "data": original_graph.serialize(format="json-ld"),
    }
    client.post("/works/", headers={"X-User": "cataloger"}, json=payload)
    stmt = select(Work)
    result = db_session.execute(stmt)
    return result.scalars().first()


def _add_instance(
    client: TestClient, file: str, work_id: int, work_derived_from: str
) -> None:
    original_graph = init_graph()
    instance_str = pathlib.Path(file).read_text()
    instance_str = instance_str.replace(
        "https://bluecore.info/works/23db8603-1932-4c3f-968c-ae584ef1b4bb",
        work_derived_from,
    )
    original_graph.parse(data=instance_str, format="json-ld")
    payload: dict[str, Any] = {
        "data": original_graph.serialize(format="json-ld"),
        "work_id": work_id,
    }
    client.post("/instances/", headers={"X-User": "cataloger"}, json=payload)


def add_instances(
    client: TestClient, db_session: Session, work_id: int, work_derived_from: str
):
    for file in ["tests/cbd-instance.jsonld", "tests/cbd-instance2.jsonld"]:
        _add_instance(client, file, work_id, work_derived_from)
    stmt = select(Instance)
    result = db_session.execute(stmt)
    return result.scalars().all()


def test_reorder_work_types():
    test_data = {
        "@type": ["Monograph", "Work", "Text"],
    }
    got = reorder_work_types(test_data)
    assert got["@type"] == ["Work", "Monograph", "Text"]

    test_data = {
        "@type": ["Work", "Monograph"],
    }
    got = reorder_work_types(test_data)
    assert got["@type"] == ["Work", "Monograph"]


def test_reorder_instance_types():
    test_data = {
        "@type": ["Physical", "Instance", "Text"],
    }
    got = reorder_instance_types(test_data)
    assert got["@type"] == ["Instance", "Physical", "Text"]

    test_data = {
        "@type": ["Instance", "Physical"],
    }
    got = reorder_instance_types(test_data)
    assert got["@type"] == ["Instance", "Physical"]


def test_cbd(client: TestClient, db_session: Session):
    work = add_work(client, db_session)
    work_id: int = work.id  # ty: ignore[unresolved-attribute]
    assert work is not None
    admin_metadata: list = work.data["adminMetadata"]  # ty: ignore[invalid-argument-type]
    work_derived_from: str = next(
        admin_md["derivedFrom"]["@id"]
        for admin_md in admin_metadata
        if "derivedFrom" in admin_md
    )
    instances = add_instances(client, db_session, work_id, work_derived_from)

    headers = {"Accept": "application/cbd+xml"}
    response = client.get(f"/instances/{instances[0].uuid!s}", headers=headers)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/rdf+xml"
    response_data = response.content.decode("utf-8")
    root = ET.fromstring(response_data)
    BF_NS = "http://id.loc.gov/ontologies/bibframe/"
    children = list(root)
    bf_children = [el for el in children if el.tag.startswith("{" + BF_NS)]
    bf_local_names = [
        el.tag.split("}", 1)[1] if "}" in el.tag else el.tag for el in bf_children
    ]
    # 1) Only Work/Instance should appear at top level in bf:* namespace
    assert set(bf_local_names).issubset({"Work", "Instance"}), (
        f"Unexpected bf:* top-level elements: {sorted(set(bf_local_names))}"
    )
    # 2) Ensure there is at least one Work and one Instance (duplicates allowed)
    assert "Work" in bf_local_names, "Missing top-level bf:Work element"
    assert "Instance" in bf_local_names, "Missing top-level bf:Instance element"


def test_cbd_other_resources(client: TestClient, db_session: Session):
    # save_graph wants a sessionmaker rather than a Session, so we make a fake one
    def sessionmaker(*args, **kwargs):
        return db_session

    # parse a CBD json-ld file
    graph = Graph()
    graph.parse("tests/23807141.jsonld")

    # persist the graph to the database
    bc_graph = BluecoreGraph(graph)
    bc_graph.save(sessionmaker)  # ty: ignore[invalid-argument-type]

    assert (
        URIRef("http://id.loc.gov/authorities/subjects/sh85065889")
        in bc_graph.graph.subjects()
    )

    # get one of the instance URIs that was created
    assert len(bc_graph.instances()) == 2
    instance_graph = bc_graph.instances()[1]

    # determine its local path
    instance_uri = next(instance_graph.subjects(RDF.type, BF.Instance))
    uuid = str(instance_uri).split("/")[-1]

    response = client.get(f"/instances/{uuid}.cbd.jsonld")
    response_graph = Graph()
    response_graph.parse(data=response.content, format=response.headers["Content-Type"])
    assert (
        URIRef("http://id.loc.gov/authorities/subjects/sh85065889")
        in response_graph.subjects()
    )

    response = client.get(f"/instances/{uuid}.cbd.jsonld")
    response_graph = Graph()
    response_graph.parse(data=response.content, format="json-ld")
    assert (
        URIRef("http://id.loc.gov/authorities/subjects/sh85065889")
        in response_graph.subjects()
    )

    instance = db_session.query(Instance).filter(Instance.uuid == uuid).first()
    assert instance is not None
    cbd_graph = generate_cbd_graph(instance)
    cbd_xml = generate_cbd_xml(cbd_graph)
    # This record has two Works, each with an Instance, and they reference each
    # other through bf:relation. LC's CBD carries all four, so ours does too.
    assert len(cbd_xml) == 4, "Expected 4 top-level elements in CBD XML"
    top_level_tags: list[BibframeType] = [BibframeType.WORK, BibframeType.INSTANCE]
    for elem in cbd_xml:
        local_name = etree.QName(elem).localname
        assert local_name in top_level_tags, (
            f"Unexpected top-level element: {local_name}"
        )
    xpath = "bf:Work/bf:contribution/bf:Contribution/bf:agent/bf:Agent[@rdf:about='http://id.loc.gov/rwo/agents/n2024040883']"
    match = cbd_xml.xpath(xpath, namespaces=XPATH_NAMESPACES)
    # Both Works credit this agent, and each nests its own copy of the description.
    assert len(match) == 2, (
        "Expected to find a matching Agent element for "
        "http://id.loc.gov/rwo/agents/n2024040883 under each Work"
    )
    for agent in match:
        label = agent.find("{http://www.w3.org/2000/01/rdf-schema#}label")
        assert label is not None, "Expected to find rdfs:label element for the Agent"
        assert label.text == "Farri, Elisa", (
            f"Expected Agent label to be 'Farri, Elisa' but got '{label.text}'"
        )


# ---------------------------------------------------------------------------
# Related Works: LC's CBD carries them, as thumbnails
# ---------------------------------------------------------------------------
ONLINE_VERSION = "http://id.loc.gov/entities/relationships/onlineversion"


def _make_work(db_session, uuid_, title, related_uri=None):
    """A Work carrying one property that a thumbnail drops (summary)."""
    uri = f"https://bluecore.info/works/{uuid_}"
    data = {
        "@id": uri,
        "@type": "Work",
        "title": {"@type": "Title", "mainTitle": title},
        "language": {"@id": "http://id.loc.gov/vocabulary/languages/eng"},
        "summary": {"@type": "Summary", "rdfs:label": f"About {title}"},
    }
    if related_uri is not None:
        data["relation"] = {
            "@type": "Relation",
            "relationship": {"@id": ONLINE_VERSION},
            "associatedResource": {"@id": related_uri},
        }
    work = Work(uuid=uuid_, uri=uri, data=data)
    db_session.add(work)
    return work


def _make_instance(db_session, uuid_, work, title):
    """An Instance carrying one property a thumbnail keeps (extent) and one it drops (note)."""
    uri = f"https://bluecore.info/instances/{uuid_}"
    instance = Instance(
        uuid=uuid_,
        uri=uri,
        work=work,
        data={
            "@id": uri,
            "@type": "Instance",
            "title": {"@type": "Title", "mainTitle": title},
            "extent": {"@type": "Extent", "rdfs:label": "1 volume"},
            "note": {"@type": "Note", "rdfs:label": f"Note on {title}"},
            "instanceOf": {"@id": work.uri},
        },
    )
    db_session.add(instance)
    return instance


def _resources(graph: Graph) -> set[str]:
    """The Work and Instance uris the CBD graph describes."""
    return {str(s) for s in graph.subjects(RDF.type, BF.Work)} | {
        str(s) for s in graph.subjects(RDF.type, BF.Instance)
    }


def _pair(db_session, tag, related_uri=None):
    work = _make_work(
        db_session,
        f"11111111-0000-0000-0000-00000000000{tag}",
        f"Work {tag}",
        related_uri,
    )
    instance = _make_instance(
        db_session, f"22222222-0000-0000-0000-00000000000{tag}", work, f"Instance {tag}"
    )
    return work, instance


def test_cbd_describes_related_work_from_either_instance(
    client: TestClient, db_session: Session
):
    """
    two Works that point at each other, each with its own Instance.
    Asking through either Instance has to describe all four, the way LC's does.
    """
    work_a, instance_a = _pair(db_session, "1")
    work_b, instance_b = _pair(db_session, "2", related_uri=work_a.uri)
    work_a.data["relation"] = {
        "@type": "Relation",
        "relationship": {"@id": ONLINE_VERSION},
        "associatedResource": {"@id": work_b.uri},
    }
    db_session.commit()

    expected = {work_a.uri, work_b.uri, instance_a.uri, instance_b.uri}
    assert _resources(generate_cbd_graph(instance_a)) == expected
    assert _resources(generate_cbd_graph(instance_b)) == expected


def test_cbd_thumbnails_the_related_work_and_its_instance(
    client: TestClient, db_session: Session
):
    """
    The requested pair is described in full; the related pair is cut down to the
    properties that identify it, as LC does. Extent survives, summary and note don't.
    """
    work_a, instance_a = _pair(db_session, "3")
    work_b, instance_b = _pair(db_session, "4")
    work_a.data["relation"] = {
        "@type": "Relation",
        "relationship": {"@id": ONLINE_VERSION},
        "associatedResource": {"@id": work_b.uri},
    }
    db_session.commit()

    graph = generate_cbd_graph(instance_a)

    # requested pair: everything
    assert (URIRef(work_a.uri), BF.summary, None) in graph
    assert (URIRef(instance_a.uri), BF.note, None) in graph

    # related pair: thumbnail only
    assert (URIRef(work_b.uri), BF.title, None) in graph
    assert (URIRef(work_b.uri), BF.summary, None) not in graph
    assert (URIRef(instance_b.uri), BF.extent, None) in graph
    assert (URIRef(instance_b.uri), BF.note, None) not in graph


def test_cbd_follows_relations_one_hop_only(client: TestClient, db_session: Session):
    """
    A points at B points at C. LC's document stops after one hop, so C stays out
    -- otherwise a chain of editions would drag in the whole chain.
    """
    work_c, instance_c = _pair(db_session, "5")
    work_b, _ = _pair(db_session, "6", related_uri=work_c.uri)
    _, instance_a = _pair(db_session, "7", related_uri=work_b.uri)
    db_session.commit()

    resources = _resources(generate_cbd_graph(instance_a))
    assert work_b.uri in resources
    assert work_c.uri not in resources
    assert instance_c.uri not in resources


def test_related_works_ignores_a_relation_described_in_place(
    client: TestClient, db_session: Session
):
    """
    LC often describes the other end of a relation inline, with no uri of its own.
    There is no record to fetch, and it already travels with the Work's own data.
    """
    work, _ = _pair(db_session, "8")
    work.data["relation"] = {
        "@type": "Relation",
        "relationship": {"@id": ONLINE_VERSION},
        "associatedResource": {
            "@id": "_:b29",
            "@type": "Work",
            "title": {"@type": "Title", "mainTitle": "Nested edition"},
        },
    }
    db_session.commit()

    assert related_works(work) == []


def test_related_works_skips_a_record_we_do_not_hold(
    client: TestClient, db_session: Session
):
    """A relation can point at something never ingested; that is not an error."""
    work, _ = _pair(db_session, "9", related_uri="https://bluecore.info/works/missing")
    db_session.commit()

    assert related_works(work) == []


def test_cbd_leaves_the_related_records_untouched(
    client: TestClient, db_session: Session
):
    """
    Serializing needs an @context on each record, and it has to go on a copy:
    these are rows we were only reading, and we shouldn't leave edits on them.

    Only the related pair is checked. The requested Instance goes through the
    model's own framing on the way in, which puts an @context back by itself.
    """
    _, instance_a = _pair(db_session, "0")
    work_b, instance_b = _pair(db_session, "a")
    instance_a.work.data["relation"] = {
        "@type": "Relation",
        "relationship": {"@id": ONLINE_VERSION},
        "associatedResource": {"@id": work_b.uri},
    }
    db_session.commit()

    generate_cbd_graph(instance_a)

    assert "@context" not in work_b.data
    assert "@context" not in instance_b.data


if __name__ == "__main__":
    pytest.main()
