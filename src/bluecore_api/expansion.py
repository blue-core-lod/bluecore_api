import json

from bluecore_models.models import Hub, Instance, ResourceBase, Work
from rdflib import RDFS, Graph, Literal, URIRef

from bluecore_api.app.utils.jsonld import load_jsonld_from_model
from bluecore_api.app.views import model


def expand_resource_graph(db_resource: Hub | Instance | Work) -> list:
    """
    Takes a Bluecore Work or Instance and iterates through the entity's
    other resources and adds the other resource RDF to the entity's graph,
    along with a label for each Work, Instance or Hub it links to.
    """
    expanded_graph = load_jsonld_from_model(db_resource.data)
    expanded_graph = expand_resource_as_graph(db_resource, expanded_graph)
    expanded_graph = add_linked_labels(db_resource, expanded_graph)
    return json.loads(expanded_graph.serialize(format="json-ld"))


def expand_resource_as_graph(db_resource: Instance | Work, graph: Graph) -> Graph:
    """
    Takes a Bluecore Work or Instance and iterates through the entity's
    other resources and adds the other resource RDF to the input graph.
    """
    for row in db_resource.other_resources:
        other_resource_graph = load_jsonld_from_model(row.other_resource.data)
        graph.parse(
            data=other_resource_graph.serialize(format="json-ld"), format="json-ld"
        )
    return graph


def add_linked_labels(db_resource: ResourceBase, graph: Graph) -> Graph:
    """
    Label each Bluecore Work, Instance or Hub the resource links to with its
    main title, as `<linked uri> rdfs:label "title"`.

    The editor names a linked resource only by its rdfs:label, so without one
    a bf:hasInstance, bf:instanceOf, bf:expressionOf or bf:hasExpression link
    loads unlabeled. Only a link the graph actually makes is labeled, and one
    the graph already labels is left as it is.
    """
    for linked in _linked_resources(db_resource):
        uri = URIRef(linked.uri)
        if (None, None, uri) not in graph or (uri, RDFS.label, None) in graph:
            continue
        title = _main_title(linked)
        if title is not None:
            graph.add((uri, RDFS.label, title))
    return graph


def _linked_resources(db_resource: ResourceBase) -> list[Hub | Instance | Work]:
    """The Works, Instances and Hubs the database links this resource to."""
    if isinstance(db_resource, Instance):
        return [db_resource.work] if db_resource.work else []
    if isinstance(db_resource, Hub):
        return list(db_resource.works)
    if isinstance(db_resource, Work):
        hub = [db_resource.hub] if db_resource.hub else []
        return [*db_resource.instances, *hub]
    return []


def _main_title(resource: Hub | Instance | Work) -> Literal | None:
    """The mainTitle of the resource's title proper, else its first mainTitle
    of any title, keeping the language tag; None if it has no mainTitle."""
    read = model.as_model(resource)
    if read is None:
        return None
    proper = [title for title in read.title if not title.is_variant]
    for title in [*proper, *read.title]:
        if title.main:
            text = title.main[0]
            return Literal(text.value, lang=text.language)
    return None
