import copy
import json
from typing import Any

from bluecore_models.models import Instance, Work
from bluecore_models.utils.graph import CONTEXT, load_jsonld
from fastapi import HTTPException
from lxml import etree
from rdflib import Graph, Namespace
from sqlalchemy.orm import object_session

from bluecore_api.constants import BibframeType
from bluecore_api.expansion import expand_resource_as_graph

BF_NAMESPACE = Namespace("http://id.loc.gov/ontologies/bibframe/")
RDF_NAMESPACE = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
MADSRDF_NAMESPACE = Namespace("http://www.loc.gov/mads/rdf/v1#")
XPATH_NAMESPACES = {
    "bf": str(BF_NAMESPACE),
    "rdf": str(RDF_NAMESPACE),
}

# Resource types kept as top-level siblings in the CBD XML instead of being
# nested inside the elements that reference them. Marva expects Works,
# Instances, and Items to stay at the top level, linked only by rdf:resource.
TOP_LEVEL_TYPES = (BibframeType.WORK, BibframeType.INSTANCE, BibframeType.ITEM)


def top_level_resource(elem) -> bool:
    """Whether an element is a Work/Instance/Item that should not be nested."""
    return any(elem.tag.endswith(bf_type) for bf_type in TOP_LEVEL_TYPES)


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


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def related_works(work: Work) -> list[Work]:
    """
    The other Works this one points at through bf:relation, e.g. the online
    edition of a printed book. LC's CBD includes them, so ours does too. Only
    ones with a uri: anything LC described in place is already in this graph.
    """
    uris = {
        item["@id"]
        for relation in _as_list(work.data.get("relation"))
        if isinstance(relation, dict)
        for item in _as_list(relation.get("associatedResource"))
        if isinstance(item, dict) and str(item.get("@id", "")).startswith("http")
    }
    session = object_session(work)
    if not uris or session is None:
        return []
    return session.query(Work).where(Work.uri.in_(uris)).all()


# LC gives a related Work and its Instances a thumbnail rather than a second full
# record: just enough to say which resource is meant. These are the properties it
# keeps. We list rdfs:label and bflc:aap both, since our records name themselves
# with "bflc:aap" where LC's use "rdfs:label".
WORK_THUMBNAIL = frozenset(
    {
        "@id",
        "@type",
        "rdfs:label",
        "bflc:aap",
        "title",
        "contribution",
        "classification",
        "language",
        "hasInstance",
    }
)
INSTANCE_THUMBNAIL = frozenset(
    {"@id", "@type", "title", "identifiedBy", "publicationStatement", "extent"}
)


def add_resource(
    graph: Graph,
    resource: Instance | Work,
    reorder,
    keep: frozenset[str] | None = None,
) -> Graph:
    """
    Add a Work/Instance and the vocabulary terms it references to the graph.

    keep trims the record to a thumbnail, and then the terms are left out too --
    a thumbnail names the resource rather than describing it. The data is copied
    first so the record we were handed keeps the shape it has in the database.
    """
    data = dict(reorder(resource.data))
    if keep is not None:
        data = {key: value for key, value in data.items() if key in keep}
    data["@context"] = CONTEXT
    graph.parse(data=json.dumps(data), format="json-ld")
    if keep is not None:
        return graph
    return expand_resource_as_graph(resource, graph)


def generate_cbd_graph(instance: Instance) -> Graph:
    """
    Generate a CBD graph for a given Instance.
    It includes the Instance, its Work, any Works that Work is related to, and
    every Instance of those Works, along with their related resources.

    Args:
        instance (Instance): The Instance for which to generate the CBD graph

    Returns:
        Graph: RDF graph containing the CBD for the given Instance
    """
    # The xml serialization uses the first @type to determine the root element,
    # so 'Work'/'Instance' has to come first in the list of types.
    instance.data = reorder_instance_types(instance.data)
    instance_graph: Graph = load_jsonld(instance.data)
    instance_graph = expand_resource_as_graph(instance, instance_graph)

    work = instance.work
    seen = {str(instance.uuid)}
    instance_graph = add_resource(instance_graph, work, reorder_work_types)
    for sibling in work.instances:
        if str(sibling.uuid) in seen:
            continue
        seen.add(str(sibling.uuid))
        instance_graph = add_resource(instance_graph, sibling, reorder_instance_types)

    # One hop only: a related Work points back here, and LC's document stops at
    # the same place. These get a thumbnail rather than a full description.
    for related_work in related_works(work):
        instance_graph = add_resource(
            instance_graph, related_work, reorder_work_types, WORK_THUMBNAIL
        )
        for related_instance in related_work.instances:
            if str(related_instance.uuid) in seen:
                continue
            seen.add(str(related_instance.uuid))
            instance_graph = add_resource(
                instance_graph,
                related_instance,
                reorder_instance_types,
                INSTANCE_THUMBNAIL,
            )

    instance_graph.bind("bf", BF_NAMESPACE, override=True, replace=True)
    instance_graph.bind("madsrdf", MADSRDF_NAMESPACE, override=True, replace=True)
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
        if top_level_resource(elem):
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
        if top_level_resource(elem):
            continue
        root.remove(elem)

    return root


def cbd_jsonld(instance: Instance) -> str:
    if isinstance(instance, Work):
        raise HTTPException(
            status_code=400, detail="CBD serialization is only supported for Instances"
        )

    instance_graph = generate_cbd_graph(instance)
    return instance_graph.serialize(format="json-ld", indent=2)


def cbd_xml(instance: Instance) -> str:
    if isinstance(instance, Work):
        raise HTTPException(
            status_code=400, detail="CBD serialization is only supported for Instances"
        )

    instance_graph = generate_cbd_graph(instance)
    instance_root = generate_cbd_xml(instance_graph)
    return etree.tostring(instance_root, encoding="utf-8").decode("utf-8")
