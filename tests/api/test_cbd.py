from bluecore_api.app.routes.cbd import reorder_work_types, reorder_instance_types
from bluecore_models.models import Instance, Work
from bluecore_models.utils.graph import init_graph
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Any, Dict, Sequence
import pathlib
import pytest
import xml.etree.ElementTree as ET


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


if __name__ == "__main__":
    pytest.main()
