import json
from typing import Any, Dict

from bluecore_models.models import Instance, ResourceBase
from bluecore_models.utils.graph import load_jsonld
from fastapi import APIRouter, Depends, HTTPException, Response
from rdflib import Namespace, Graph
from sqlalchemy.orm import Session

from bluecore_api.constants import BibframeType
from bluecore_api.database import get_db

endpoints = APIRouter()


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


def add_other_resources(resource: ResourceBase, graph: Graph):
    for bf_other in resource.other_resources:
        graph.parse(data=bf_other.other_resource.data, format="json-ld")


@endpoints.get("/cbd/{instance_uuid}", operation_id="get_cbd")
async def cbd(instance_uuid: str, response: Response, db: Session = Depends(get_db)):
    # Marva editor expects the request url to end with .rdf
    effective_uuid = instance_uuid.strip().replace(".rdf", "").replace(".jsonld", "")
    db_instance = db.query(Instance).filter(Instance.uuid == effective_uuid).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    reordered_instance_data = reorder_instance_types(db_instance.data)
    graph = load_jsonld(reordered_instance_data)
    add_other_resources(db_instance, graph)

    work = db_instance.work
    # The xml serialization uses the first @type to determine the root element
    # Make sure 'Work' is the first in the list of types for the work
    reordered_work_data = reorder_work_types(work.data)
    graph.parse(data=json.dumps(reordered_work_data), format="json-ld")
    add_other_resources(work, graph)

    # If the work has multiple instances, include them in the graph
    for related_instance in work.instances:
        if str(related_instance.uuid) != effective_uuid:
            add_other_resources(related_instance, graph)
            related_instance_data = reorder_instance_types(related_instance.data)
            graph.parse(data=json.dumps(related_instance_data), format="json-ld")

    if instance_uuid.endswith(".jsonld"):
        jsonld_content = graph.serialize(format="json-ld", indent=2)
        return Response(
            content=jsonld_content,
            media_type="application/json",
        )

    bf_namespace = Namespace("http://id.loc.gov/ontologies/bibframe/")
    graph.bind("bf", bf_namespace, override=True, replace=True)
    xml_content = graph.serialize(format="pretty-xml", indent=1, xml_declaration=False)

    return Response(
        content=xml_content,
        media_type="application/rdf+xml",
    )
