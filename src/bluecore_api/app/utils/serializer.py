from collections.abc import Callable, Iterator

from bluecore_models.models import Hub, Instance, Work
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

type SerializerFn = Callable[[Hub | Instance | Work, bool], Response | None]
serializer_format_registry: dict[str, SerializerFn] = {
    "cbd.jsonld": as_cbd_jsonld,
    "cbd.xml": as_cbd_xml,
    "json": as_jsonld,
    "jsonld": as_jsonld,
    "nt": as_ntriples,
    "rdf": as_rdfxml,
    "ttl": as_turtle,
    "vnd.sinopia.json": as_vnd_sinopia_json,
}

serializer_accept_registry: dict[str, SerializerFn] = {
    "application/cbd+jsonld": as_cbd_jsonld,
    "application/cbd+xml": as_cbd_xml,
    "application/json": as_jsonld,
    "application/ld+json": as_jsonld,
    "application/n-triples": as_ntriples,
    "application/rdf+xml": as_rdfxml,
    "application/vnd.sinopia+json": as_vnd_sinopia_json,
    "text/turtle": as_turtle,
}


def accept_media_types(accept_header: str) -> Iterator[str]:
    """Yield the requested media types, in the order the client listed them.

    `q=` parameters are stripped rather than ranked, so the client's ordering
    decides and not its weights. An empty or absent header yields one empty
    string, which callers can treat as "no preference".

    What to do with a wildcard, or with a header naming nothing available, is
    left to the caller: the resource routes fall back to HTML, while
    app/routes/convert.py defaults to JSON-LD and raises 406.
    """
    for accept_raw in accept_header.split(","):
        yield accept_raw.split(";")[0].strip()


def serialize(
    doc: Hub | Instance | Work, expand: bool, format: str | None, request: Request
) -> Response | None:
    if format in serializer_format_registry:
        return serializer_format_registry[format](doc, expand)
    for accept in accept_media_types(request.headers.get("accept", "")):
        if (
            accept == "text/html"
        ):  # HTML is reached by content negotiation "Accept: text/html"
            return as_html(doc, request)
        if accept in serializer_accept_registry:
            return serializer_accept_registry[accept](doc, expand)
    return None
