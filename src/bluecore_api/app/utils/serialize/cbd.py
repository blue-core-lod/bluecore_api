import copy
import json
from collections.abc import Callable, Sequence
from typing import Any

import bibframe_json
from bluecore_models.models import Instance, Work
from bluecore_models.utils.graph import CONTEXT, terms_for
from fastapi import HTTPException
from lxml import etree
from pyld import jsonld
from rdflib import Graph, Namespace
from sqlalchemy.orm import object_session

from bluecore_api.app.utils.jsonld import load_jsonld_from_model, model_data_as_dict
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


def reorder_work_types(work_data: dict[str, object]) -> dict[str, object]:
    """Reorder work types to ensure 'Work' is first"""
    types = work_data.get("@type")
    if isinstance(types, list):
        types.sort(key=lambda x: x != BibframeType.WORK)
    return work_data


def reorder_instance_types(instance_data: dict[str, object]) -> dict[str, object]:
    """Reorder instance types to ensure 'Instance' is first"""
    types = instance_data.get("@type")
    if isinstance(types, list):
        types.sort(key=lambda x: x != BibframeType.INSTANCE)
    return instance_data


def _as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def related_works(work: Work) -> list[Work]:
    """
    The other Works this one points at through bf:relation, e.g. the online
    edition of a printed book. LC's CBD includes them, so ours does too. Only
    ones with a uri: anything LC described in place is already in this graph.
    """
    data = model_data_as_dict(work.data)
    uris = {
        item["@id"]
        for relation in _as_list(data.get("relation"))
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

type _Reorder = Callable[[dict[str, object]], dict[str, object]]


def add_resource(
    graph: Graph,
    resource: Instance | Work,
    reorder: _Reorder,
    keep: frozenset[str] | None = None,
) -> Graph:
    """
    Add a Work/Instance and the vocabulary terms it references to the graph.

    keep trims the record to a thumbnail, and then the terms are left out too --
    a thumbnail names the resource rather than describing it. The data is copied
    first so the record we were handed keeps the shape it has in the database.
    """
    data = dict(reorder(model_data_as_dict(resource.data)))
    if keep is not None:
        data = {key: value for key, value in data.items() if key in keep}
    # Resolved here and handed over as context=, so rdflib never fetches it.
    terms = terms_for(data)
    data.pop("@context", None)
    graph.parse(data=json.dumps(data), format="json-ld", context=terms)
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
    instance.data = reorder_instance_types(model_data_as_dict(instance.data))  # ty: ignore[invalid-assignment]
    instance_graph: Graph = load_jsonld_from_model(instance.data)
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


def generate_cbd_xml(graph: Graph, primary_uris: Sequence[str] = ()):
    """
    Generate CBD XML representation.
    The pretty-xml format generates all other resources at the same level as Work/Instance(s).
    Marva cannot parse this format properly.
    This method reorders the XML so that the related resources are nested within Work/Instance(s).

    rdflib serializes subjects in no fixed order, and Marva loads the first
    top-level Work and Instance it finds. So the top-level resources are put in
    a stable order: primary_uris first, as given, then the rest sorted by uri.

    Args:
        graph (Graph): CBD graph
        primary_uris (Sequence[str]): uris of the resources to put first, e.g. the
            requested Instance and its Work

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

    primary = {uri: position for position, uri in enumerate(primary_uris)}

    def position(elem) -> tuple[int, str]:
        about = elem.xpath("@rdf:about", namespaces=XPATH_NAMESPACES)
        uri = str(about[0]) if about else ""
        return primary.get(uri, len(primary)), uri

    # appending an element lxml already holds moves it to the end
    for elem in sorted(root, key=position):
        root.append(elem)

    return root


def bounded_description(instance: Instance) -> dict[str, Any]:
    """
    The CBD as bibframe-json's bounded description: the Instance at the root,
    its Work embedded under instanceOf, and everything else described where it
    is first referenced.

    The graph is the same one cbd.xml serializes, and so are the triples; only
    the arrangement differs. RDF/XML has no natural root, so LC's CBD puts the
    principal resources side by side, which is what Marva reads. JSON has one,
    so here the document is the Instance, and a client reads it without
    rejoining URIs.
    """
    return frame_bounded(generate_cbd_graph(instance), instance.uri)


def frame_bounded(graph: Graph, instance_uri: str) -> dict[str, Any]:
    """
    Any BIBFRAME graph framed as a bounded description rooted at one Instance:
    a CBD from Blue Core, or a description from elsewhere (see the /frame
    route).

    These are the steps bibframe-json gives for producing the shape
    (example/produce.py there). Framing is one of them; the others are what
    framing won't do: make every property an array, drop the blank node labels
    framing invents, and name the context by URL instead of inlining its 12,000
    bytes. "@embed": "@once" describes a resource the first time it is reached
    and references it after, which keeps the document finite: the Work's
    hasInstance points back to the root by URI.
    """
    expanded = json.loads(graph.serialize(format="json-ld"))
    framed = jsonld.frame(
        expanded,
        {
            "@context": CONTEXT,
            "@id": instance_uri,
            "@embed": "@once",
            "@omitDefault": True,
        },
    )
    document = without_blank_ids(as_arrays(framed))
    document["@context"] = bibframe_json.CONTEXT_URL
    return document


# Keywords holding one value by definition, which the array rule doesn't reach.
SINGULAR_KEYWORDS = ("@context", "@id", "@value", "@language", "@direction", "@index")


def as_arrays(node: Any) -> Any:
    """
    Every property an array, which the context's @container: @set promises only
    for the terms it declares. @type is a list of classes on a node, so it is
    wrapped, but one datatype IRI on a value object, so it is not.
    """
    if isinstance(node, list):
        return [as_arrays(item) for item in node]
    if not isinstance(node, dict):
        return node
    literal = "@value" in node
    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in SINGULAR_KEYWORDS:
            result[key] = value
        elif key == "@type":
            result[key] = value if literal or isinstance(value, list) else [value]
        else:
            listed = value if isinstance(value, list) else [value]
            result[key] = [as_arrays(item) for item in listed]
    return result


def without_blank_ids(node: Any) -> Any:
    """
    Drop the _:b0-style @id framing gives a node that has none. bibframe-json
    forbids an @id on a blank node: it addresses nothing outside the document,
    and keeping it would make two identical values differ by accident.

    A reference to a blank node goes too, along with a property it leaves
    empty. Framing writes one when it reaches a blank node it has already
    embedded, as when an unnamed related Work's unnamed Instance points back
    at it with instanceOf. Once the node's own label is gone, the reference
    would name nothing, and a client saving the document back would make it a
    new, empty node. What it said is the inverse of the property it sits
    under (instanceOf below hasInstance), which Blue Core's loader adds back.
    """
    if isinstance(node, list):
        return [
            without_blank_ids(item) for item in node if not is_blank_reference(item)
        ]
    if not isinstance(node, dict):
        return node
    result: dict[str, Any] = {}
    for key, value in node.items():
        if key == "@id" and isinstance(value, str) and value.startswith("_:"):
            continue
        kept = without_blank_ids(value)
        if isinstance(value, list) and value and kept == []:
            continue
        result[key] = kept
    return result


def is_blank_reference(value: Any) -> bool:
    """A value that only points at a blank node by its label: "_:b13" or {"@id": "_:b13"}."""
    if isinstance(value, dict) and set(value) == {"@id"}:
        value = value["@id"]
    return isinstance(value, str) and value.startswith("_:")


def cbd_jsonld(instance: Instance) -> str:
    if isinstance(instance, Work):
        raise HTTPException(
            status_code=400, detail="CBD serialization is only supported for Instances"
        )

    return json.dumps(bounded_description(instance), indent=2)


def cbd_xml(instance: Instance) -> str:
    if isinstance(instance, Work):
        raise HTTPException(
            status_code=400, detail="CBD serialization is only supported for Instances"
        )

    instance_graph = generate_cbd_graph(instance)
    instance_root = generate_cbd_xml(instance_graph, [instance.uri, instance.work.uri])
    return etree.tostring(instance_root, encoding="utf-8").decode("utf-8")
