from collections.abc import Callable, Iterator

from bluecore_models.models import Hub, Instance, Work
from fastapi import Request, Response

from bluecore_api.app.utils.etag import resource_etag
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
    decides and not its weights. Media types are lowercased, since RFC 9110
    makes them case-insensitive. An empty or absent header yields one empty
    string, which callers can treat as "no preference".

    What to do with a wildcard, or with a header naming nothing available, is
    left to the caller: the resource routes fall back to HTML, while
    app/routes/convert.py defaults to JSON-LD and raises 406.
    """
    for accept_raw in accept_header.split(","):
        # Lowercased because RFC 9110 makes type/subtype case-insensitive, and
        # both registries here are keyed in lower case.
        yield accept_raw.split(";")[0].strip().lower()


# CBD bundles the Instance with its Work and the Work's other Instances, so it
# changes when any of them do, and an Instance's ETag can't vouch for it.
COMPOSITE_SERIALIZERS: set[SerializerFn] = {as_cbd_jsonld, as_cbd_xml}


def with_etag(
    serializer: SerializerFn, doc: Hub | Instance | Work, expand: bool
) -> Response | None:
    """Run a serializer, adding an ETag when the response is the stored resource.

    The ETag (see app/utils/etag.py) is what a client sends back in If-Match to
    PUT or DELETE a Work or Instance, so it is only given where the response is
    that one stored resource, in some RDF serialization. An expanded response
    folds in the labels and descriptions of the resources it links to, which
    change without this resource's ETag moving; CBD likewise brings in other
    resources. A strong ETag on those would claim they hadn't changed when they
    had, so they go without. Hubs have no conditional writes yet.

    The one ETag is shared by every serialization of a resource, since they are
    all renderings of the same stored data and If-Match on a write has to accept
    whichever one the client read.

    HTML isn't served through here (see serialize): it is a page for people,
    with linked labels and sidebars drawn from other resources, not something
    an editor reads in order to save.
    """
    response = serializer(doc, expand)
    if (
        response is not None
        and isinstance(doc, (Instance, Work))
        and not expand
        and serializer not in COMPOSITE_SERIALIZERS
    ):
        response.headers["ETag"] = resource_etag(doc)
    return response


def serialize(
    doc: Hub | Instance | Work, expand: bool, format: str | None, request: Request
) -> Response | None:
    if format in serializer_format_registry:
        return with_etag(serializer_format_registry[format], doc, expand)
    for accept in accept_media_types(request.headers.get("accept", "")):
        if (
            accept == "text/html"
        ):  # HTML is reached by content negotiation "Accept: text/html"
            return as_html(doc, request)
        if accept in serializer_accept_registry:
            return with_etag(serializer_accept_registry[accept], doc, expand)
    return None
