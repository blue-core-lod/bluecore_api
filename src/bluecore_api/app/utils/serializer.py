from typing import Callable

from bluecore_models.models import Instance, Work
from fastapi import Request, Response

from bluecore_api.app.utils.serialize.response_generator import (
    as_cbd_jsonld,
    as_cbd_xml,
    as_html,
    as_jsonld,
    as_ntriples,
    as_rdfxml,
    as_turtle,
    as_vnd_sinopia_json,
)

type SerializerFn = Callable[[Instance | Work, bool], Response | None]
serializer_format_registry: dict[str, SerializerFn] = {
    "cbd.jsonld": as_cbd_jsonld,
    "cbd.xml": as_cbd_xml,
    "jsonld": as_jsonld,
    "nt": as_ntriples,
    "rdf": as_rdfxml,
    "ttl": as_turtle,
    "vnd.sinopia.json": as_vnd_sinopia_json,
}

serializer_accept_registry: dict[str, SerializerFn] = {
    "application/cbd+jsonld": as_cbd_jsonld,
    "application/cbd+xml": as_cbd_xml,
    "application/ld+json": as_jsonld,
    "application/n-triples": as_ntriples,
    "application/rdf+xml": as_rdfxml,
    "application/vnd.sinopia+json": as_vnd_sinopia_json,
    "text/turtle": as_turtle,
}


def serialize(
    doc: Instance | Work, expand: bool, format: str | None, request: Request
) -> Response | None:
    if format in serializer_format_registry:
        return serializer_format_registry[format](doc, expand)
    accept_header = request.headers.get("accept", "")
    if accept_header is None:
        return as_html(doc, request)  # Absent Accept header goes to the HTML view
    for accept in accept_header.split(","):
        accept = accept.split(";")[0].strip()
        if (
            accept == "text/html"
        ):  # HTML is reached by content negotiation "Accept: text/html"
            return as_html(doc, request)
        if accept in serializer_accept_registry:
            return serializer_accept_registry[accept](doc, expand)
    return None
