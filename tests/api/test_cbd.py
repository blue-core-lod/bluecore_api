import pathlib
import xml.etree.ElementTree as ET
from typing import Any, Dict, Sequence

import pytest
from bluecore_models.bluecore_graph import BluecoreGraph
from bluecore_models.models import Instance, Work
from bluecore_models.namespaces import BF
from bluecore_models.utils.graph import init_graph
from fastapi.testclient import TestClient
from rdflib import Graph, RDF, URIRef
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluecore_api.app.routes.cbd import reorder_instance_types, reorder_work_types


def add_work(client: TestClient, db_session: Session) -> Work:
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
    payload: Dict[str, Any] = {
        "data": original_graph.serialize(format="json-ld"),
        "work_id": work_id,
    }
    client.post("/instances/", headers={"X-User": "cataloger"}, json=payload)


def add_instances(
    client: TestClient, db_session: Session, work_id: int, work_derived_from: str
) -> Sequence[Instance]:
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
    work_id: int = work.id
    work_derived_from: str = work.data["derivedFrom"]["@id"]
    instances = add_instances(client, db_session, work_id, work_derived_from)

    response = client.get(f"/cbd/{str(instances[0].uuid)}.rdf")
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
    bc_graph.save(sessionmaker)

    assert (
        URIRef("http://id.loc.gov/authorities/subjects/sh85065889")
        in bc_graph.graph.subjects()
    )

    # get one of the instance URIs that was created
    assert len(bc_graph.instances()) == 2
    instance_graph = bc_graph.instances()[1]

    # determine its local path
    instance_uri = next(instance_graph.subjects(RDF.type, BF.Instance))
    uuid = instance_uri.split("/")[-1]

    response = client.get(f"/cbd/{uuid}.rdf")
    response_graph = Graph()
    response_graph.parse(data=response.content, format=response.headers["Content-Type"])
    assert (
        URIRef("http://id.loc.gov/authorities/subjects/sh85065889")
        in response_graph.subjects()
    )

    response = client.get(f"/cbd/{uuid}.jsonld")
    response_graph = Graph()
    response_graph.parse(data=response.content, format="json-ld")
    assert (
        URIRef("http://id.loc.gov/authorities/subjects/sh85065889")
        in response_graph.subjects()
    )


if __name__ == "__main__":
    pytest.main()
