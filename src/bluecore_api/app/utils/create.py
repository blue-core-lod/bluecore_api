"""Saving the resource a POST creates."""

import json
from typing import Annotated

from bluecore_models.bluecore_graph import BluecoreGraph
from bluecore_models.utils.graph import NEW_RESOURCE, load_jsonld
from fastapi import Query
from rdflib import RDF, Graph, URIRef
from sqlalchemy.orm import sessionmaker

#: The query parameter a create route takes to leave out bf:derivedFrom. The
#: editor's MARC import sends false: /marc2bibframe mints placeholder URIs under
#: http://example.org/ that name nothing, so recording them as the source of
#: the new resource would be wrong (sinopia_editor#271).
RecordDerivedFrom = Annotated[
    bool,
    Query(
        description=(
            "Record each URI the payload gives a resource as `bf:derivedFrom` "
            "on the Blue Core resource minted for it. Pass `false` when those "
            "URIs name nothing, such as the placeholders `/marc2bibframe` "
            "mints. A resource already holding a `derivedFrom` for one of them "
            "is still matched."
        ),
    ),
]


def load_new_resource(data: str) -> Graph:
    """Parse a POST body, so that an empty @id names the resource it creates."""
    return load_jsonld(json.loads(data), base=NEW_RESOURCE)


def save_new_resource(
    session_maker: sessionmaker,
    graph: Graph,
    namespace: str,
    primary_class: URIRef,
    record_derived_from: bool = True,
) -> str:
    """Save a POSTed graph and return the URI of the resource it created."""
    bluecore_graph = BluecoreGraph(
        graph, namespace, record_derived_from=record_derived_from
    )
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
