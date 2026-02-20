import json

from rdflib import Graph

from bluecore_models.models import Instance, Work
from bluecore_models.utils.graph import load_jsonld


def expand_resource_graph(db_resource: Instance | Work) -> list:
    """
    Takes a Bluecore Work or Instance and iterates through the entity's
    other resources and adds the other resource RDF to the entity's graph.
    """
    expanded_graph = load_jsonld(db_resource.data)
    expanded_graph = expand_resource_as_graph(db_resource, expanded_graph)
    return json.loads(expanded_graph.serialize(format="json-ld"))


def expand_resource_as_graph(db_resource: Instance | Work, graph: Graph) -> Graph:
    """
    Takes a Bluecore Work or Instance and iterates through the entity's
    other resources and adds the other resource RDF to the input graph.
    """
    for row in db_resource.other_resources:
        other_resource_graph = load_jsonld(row.other_resource.data)
        graph.parse(
            data=other_resource_graph.serialize(format="json-ld"), format="json-ld"
        )
    return graph
