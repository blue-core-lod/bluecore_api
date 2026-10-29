"""Saving the resource a POST creates."""

import json

from bluecore_models.bluecore_graph import BluecoreGraph
from bluecore_models.utils.graph import NEW_RESOURCE, load_jsonld
from rdflib import RDF, Graph, URIRef
from sqlalchemy.orm import sessionmaker


def load_new_resource(data: str) -> Graph:
    """Parse a POST body, so that an empty @id names the resource it creates."""
    return load_jsonld(json.loads(data), base=NEW_RESOURCE)


def save_new_resource(
    session_maker: sessionmaker, graph: Graph, namespace: str, primary_class: URIRef
) -> str:
    """Save a POSTed graph and return the URI of the resource it created."""
    bluecore_graph = BluecoreGraph(graph, namespace)
    bluecore_graph.save(session_maker, primary_class=primary_class)
    if bluecore_graph.created_uri is not None:
        return str(bluecore_graph.created_uri)
    # A payload can give the resource a URI of its own instead of a blank node,
    # which save() replaces with a Blue Core one rather than minting.
    return str(
        next(
            s
            for s in bluecore_graph.graph.subjects(RDF.type, primary_class)
            if isinstance(s, URIRef)
        )
    )
