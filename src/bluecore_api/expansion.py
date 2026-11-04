import json

from bluecore_models.models import Hub, Instance, OtherResource, ResourceBase, Work
from bluecore_models.utils.graph import framed_for_storage
from rdflib import RDFS, Graph, Literal, URIRef
from sqlalchemy import select
from sqlalchemy.orm import Session

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
        _add_other_resource(graph, row.other_resource)
    return graph


def expand_version_graph(
    db: Session, db_resource: Hub | Instance | Work, data: dict
) -> dict:
    """
    expand_resource_graph for a historical version of a resource, framed as the
    live route's expanded data is when it is assigned to the model.

    The live expansion follows the links the database holds now. A version
    follows the links its own RDF makes instead: the other resources and the
    Works, Instances and Hubs it names, looked up by URI. So a subject or Work
    the resource has since dropped is still filled in, and one added later is
    not. What a link resolves to -- an other resource's RDF, a Work's title --
    is read as it is now, as only the versioned resource itself has a history.
    """
    graph = load_jsonld_from_model(data)  # ty: ignore[invalid-argument-type]
    uris = {str(o) for o in graph.objects() if isinstance(o, URIRef)}
    uris.discard(str(db_resource.uri))
    linked = (
        db.scalars(select(ResourceBase).where(ResourceBase.uri.in_(uris))).all()
        if uris
        else []
    )
    for resource in linked:
        if isinstance(resource, OtherResource):
            _add_other_resource(graph, resource)
    _label_links(graph, [r for r in linked if isinstance(r, Hub | Instance | Work)])
    expanded = json.loads(graph.serialize(format="json-ld"))
    return framed_for_storage(str(db_resource.uri), expanded)


def _add_other_resource(graph: Graph, other_resource: OtherResource) -> None:
    other_resource_graph = load_jsonld_from_model(other_resource.data)
    graph.parse(data=other_resource_graph.serialize(format="json-ld"), format="json-ld")


def add_linked_labels(db_resource: ResourceBase, graph: Graph) -> Graph:
    """
    Label each Bluecore Work, Instance or Hub the resource links to with its
    main title, as `<linked uri> rdfs:label "title"`.

    The editor names a linked resource only by its rdfs:label, so without one
    a bf:hasInstance, bf:instanceOf, bf:expressionOf or bf:hasExpression link
    loads unlabeled. Only a link the graph actually makes is labeled, and one
    the graph already labels is left as it is.
    """
    return _label_links(graph, _linked_resources(db_resource))


def _label_links(graph: Graph, linked_resources: list[Hub | Instance | Work]) -> Graph:
    for linked in linked_resources:
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
    of any title, keeping the language tag; None if it has no mainTitle.

    A language tag rdflib rejects, such as "en_US", is dropped rather than
    failing the whole response over one linked record's title.
    """
    read = model.as_model(resource)
    if read is None:
        return None
    proper = [title for title in read.title if not title.is_variant]
    for title in [*proper, *read.title]:
        if title.main:
            text = title.main[0]
            try:
                return Literal(text.value, lang=text.language)
            except ValueError:
                return Literal(text.value)
    return None
