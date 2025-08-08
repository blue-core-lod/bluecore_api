from bluecore_api.database import get_db
from bluecore_api.constants import BibframeType
from bluecore_models.models import Instance, Work
from bluecore_models.utils.graph import load_jsonld
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Any, Dict
import json
import xml.etree.ElementTree as ET

endpoints = APIRouter()


def rename_namespace(root: ET.Element) -> ET.Element:
    nsmap = {
        "http://id.loc.gov/ontologies/bibframe/": "bf",
        "http://id.loc.gov/ontologies/bflc/": "bflc",
        "http://www.loc.gov/mads/rdf/v1#": "mads",
        "http://www.w3.org/2000/01/rdf-schema#": "rdfs",
    }

    def update_tag(tag: str, nsmap: Dict[str, str]) -> str:
        if tag[0] == "{":
            uri, local = tag[1:].split("}", 1)
            prefix = nsmap.get(uri)
            if prefix:
                return f"{prefix}:{local}"
        return tag

    for elem in root.iter():
        elem.tag = update_tag(elem.tag, nsmap)
        # Optionally update attributes with namespaces
        new_attrib: Dict[str, str] = {}
        for k, v in elem.attrib.items():
            new_k = update_tag(k, nsmap)
            new_attrib[new_k] = v
        elem.attrib.clear()
        elem.attrib.update(new_attrib)

    # Add correct namespaces
    root.set("xmlns:bf", "http://id.loc.gov/ontologies/bibframe/")
    root.set("xmlns:bflc", "http://id.loc.gov/ontologies/bflc/")
    root.set("xmlns:mads", "http://www.loc.gov/mads/rdf/v1#")
    root.set("xmlns:rdfs", "http://www.w3.org/2000/01/rdf-schema#")
    return root


def reorder_work_types(work_data: Dict[str, Any]) -> Dict[str, Any]:
    """Reorder work types to ensure 'Work' is first"""
    if isinstance(work_data.get("@type"), list):
        work_data["@type"].sort(key=lambda x: x != BibframeType.WORK)  # type: ignore
    return work_data


def reorder_instance_types(instance_data: Dict[str, Any]) -> Dict[str, Any]:
    """Reorder instance types to ensure 'Instance' is first"""
    if isinstance(instance_data.get("@type"), list):
        instance_data["@type"].sort(key=lambda x: x != BibframeType.INSTANCE)  # type: ignore
    return instance_data


@endpoints.get("/cbd/{instance_uuid}")
async def cbd(instance_uuid: str, response: Response, db: Session = Depends(get_db)):
    # Marva editor expects the request url to end with .rdf
    instance_uuid = instance_uuid.strip().replace(".rdf", "")
    db_instance = db.query(Instance).filter(Instance.uuid == instance_uuid).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    reordered_instance_data = reorder_instance_types(db_instance.data)
    graph = load_jsonld(reordered_instance_data)

    work = db_instance.work
    # The xml serialization uses the first @type to determine the root element
    # Make sure 'Work' is the first in the list of types for the work
    reordered_work_data = reorder_work_types(work.data)
    graph.parse(data=json.dumps(reordered_work_data), format="json-ld")

    # If the work has multiple instances, include them in the graph
    for related_instance in work.instances:
        if str(related_instance.uuid) != instance_uuid:
            related_instance_data = reorder_instance_types(related_instance.data)
            graph.parse(data=json.dumps(related_instance_data), format="json-ld")

    # For Marva editor, the response cannot contain xml declaration
    xml_content = graph.serialize(format="pretty-xml", max_depth=1, indent=2)
    root = ET.fromstring(xml_content)
    # The xml serialization uses generic namespaces such as ns1, ns2, etc.
    # The Marva editor requires bf namespace.
    root = rename_namespace(root)

    return Response(
        content=ET.tostring(root, encoding="utf-8").decode("utf-8"),
        media_type="application/rdf+xml",
    )
