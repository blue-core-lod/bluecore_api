import json

from bluecore_models.models import Instance, Work
from bluecore_models.utils.graph import load_jsonld
from fastapi import HTTPException, Response

from bluecore_api.app.utils.serialize.cbd import (
    cbd_jsonld,
    cbd_xml,
)
from bluecore_api.expansion import expand_resource_as_graph, expand_resource_graph
from bluecore_api.schemas.schemas import InstanceSchema, WorkSchema


def create_response(
    doc: Instance | Work, expand: bool, format: str, return_type: str
) -> Response:
    graph = load_jsonld(doc.data)
    if expand:
        graph = expand_resource_as_graph(doc, graph)
    return Response(
        content=graph.serialize(format=format),
        media_type=return_type,
    )


# For CBD, we always expand the full graph and don't use expand parameter


def as_cbd_jsonld(doc: Instance | Work, expand: bool) -> Response:
    if isinstance(doc, Work):
        raise HTTPException(
            status_code=400, detail="CBD serialization is only supported for Instances"
        )
    return Response(
        content=cbd_jsonld(doc),
        media_type="application/ld+json",
    )


def as_cbd_xml(doc: Instance | Work, expand: bool) -> Response:
    if isinstance(doc, Work):
        raise HTTPException(
            status_code=400, detail="CBD serialization is only supported for Instances"
        )
    return Response(
        content=cbd_xml(doc),
        media_type="application/rdf+xml",
    )


def as_html(doc: Instance | Work, expand: bool) -> Response:
    return Response(
        content="<html><body><h1>HTML serialization not yet implemented</h1></body></html>",
        media_type="text/html",
    )


def as_jsonld(doc: Instance | Work, expand: bool) -> Response:
    jsonld_content = jsonld(doc, expand)
    return Response(
        content=json.dumps(jsonld_content.data),
        media_type="application/ld+json",
    )


def as_ntriples(doc: Instance | Work, expand: bool) -> Response:
    return create_response(doc, expand, "nt", "application/n-triples")


def as_rdfxml(doc: Instance | Work, expand: bool) -> Response:
    return create_response(doc, expand, "xml", "application/rdf+xml")


def as_turtle(doc: Instance | Work, expand: bool) -> Response:
    return create_response(doc, expand, "turtle", "text/turtle")


def as_vnd_sinopia_json(doc: Instance | Work, expand: bool) -> Response:
    return Response(
        content=jsonld(doc, expand).model_dump_json(),
        media_type="application/ld+json",
    )


def jsonld(doc: Instance | Work, expand: bool) -> InstanceSchema | WorkSchema:
    if expand:
        doc.data = expand_resource_graph(doc)
    if isinstance(doc, Instance):
        return InstanceSchema.model_validate(doc)
    else:
        return WorkSchema.model_validate(doc)
