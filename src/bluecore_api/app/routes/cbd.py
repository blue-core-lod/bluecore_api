import copy
import json

from fastapi import APIRouter, Depends, HTTPException, Response
from lxml import etree
from rdflib import Graph, Namespace
from sqlalchemy.orm import Session
from typing import Any

from bluecore_api.database import get_db
from bluecore_api.constants import BibframeType
from bluecore_api.expansion import expand_resource_as_graph
from bluecore_models.models import Instance
from bluecore_models.utils.graph import load_jsonld


endpoints = APIRouter()

BF_NAMESPACE = Namespace("http://id.loc.gov/ontologies/bibframe/")
RDF_NAMESPACE = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
XPATH_NAMESPACES = {
    "bf": str(BF_NAMESPACE),
    "rdf": str(RDF_NAMESPACE),
}


def reorder_work_types(work_data: dict[str, Any]) -> dict[str, Any]:
    """Reorder work types to ensure 'Work' is first"""
    if isinstance(work_data.get("@type"), list):
        work_data["@type"].sort(key=lambda x: x != BibframeType.WORK)  # type: ignore
    return work_data


def reorder_instance_types(instance_data: dict[str, Any]) -> dict[str, Any]:
    """Reorder instance types to ensure 'Instance' is first"""
    if isinstance(instance_data.get("@type"), list):
        instance_data["@type"].sort(key=lambda x: x != BibframeType.INSTANCE)  # type: ignore
    return instance_data


@endpoints.get("/cbd/{instance_uuid}", operation_id="get_cbd")
async def cbd(instance_uuid: str, db: Session = Depends(get_db)):
    # Marva editor expects the request url to end with .rdf
    effective_uuid = instance_uuid.strip().replace(".rdf", "").replace(".jsonld", "")
    db_instance = db.query(Instance).filter(Instance.uuid == effective_uuid).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    instance_graph = generate_cbd_graph(db_instance)

    if instance_uuid.endswith(".jsonld"):
        jsonld_content = instance_graph.serialize(format="json-ld", indent=2)
        return Response(
            content=jsonld_content,
            media_type="application/json",
        )

    instance_root = generate_cbd_xml(instance_graph)
    xml_content = etree.tostring(instance_root, encoding="utf-8").decode("utf-8")
    return Response(
        content=xml_content,
        media_type="application/rdf+xml",
    )


def generate_cbd_graph(instance: Instance) -> Graph:
    """
    Generate a CBD graph for a given Instance.
    It includes the Instance, its Work, and any other Instances of that Work, along with their related resources.

    Args:
        instance (Instance): The Instance for which to generate the CBD graph

    Returns:
        Graph: RDF graph containing the CBD for the given Instance
    """
    instance.data = reorder_instance_types(instance.data)
    instance_graph: Graph = load_jsonld(instance.data)
    instance_graph = expand_resource_as_graph(instance, instance_graph)

    work = instance.work
    # The xml serialization uses the first @type to determine the root element
    # Make sure 'Work' is the first in the list of types for the work
    work.data = reorder_work_types(work.data)
    instance_graph.parse(data=json.dumps(work.data), format="json-ld")
    instance_graph = expand_resource_as_graph(work, instance_graph)

    uuid = str(instance.uuid)
    # If the work has multiple instances, include them in the graph
    for related_instance in work.instances:
        if uuid != str(related_instance.uuid):
            related_instance.data = reorder_instance_types(related_instance.data)
            instance_graph.parse(
                data=json.dumps(related_instance.data), format="json-ld"
            )
            instance_graph = expand_resource_as_graph(related_instance, instance_graph)

    instance_graph.bind("bf", BF_NAMESPACE, override=True, replace=True)
    return instance_graph


def generate_cbd_xml(graph: Graph):
    """
    Generate CBD XML representation.
    The pretty-xml format generates all other resources at the same level as Work/Instance(s).
    Marva cannot parse this format properly.
    This method reorders the XML so that the related resources are nested within Work/Instance(s).

    Args:
        graph (Graph): CBD graph

    Returns:
        lxml root element for the CBD XML
    """
    root = etree.fromstring(
        graph.serialize(format="pretty-xml", indent=2, max_depth=1).encode("utf-8")
    )
    for elem in root:
        if elem.tag.endswith(BibframeType.WORK) or elem.tag.endswith(
            BibframeType.INSTANCE
        ):
            continue

        about = elem.xpath("@rdf:about", namespaces=XPATH_NAMESPACES)
        if not about:
            continue

        matches = root.findall(
            f".//*[@rdf:resource='{about[0]}']", namespaces=XPATH_NAMESPACES
        )
        for match in matches:
            etree.strip_attributes(match, f"{{{RDF_NAMESPACE}}}resource")
            match.append(copy.deepcopy(elem))

    for elem in root:
        if elem.tag.endswith(BibframeType.WORK) or elem.tag.endswith(
            BibframeType.INSTANCE
        ):
            continue
        root.remove(elem)

    return root
