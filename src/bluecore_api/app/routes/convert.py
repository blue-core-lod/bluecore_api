from typing import Annotated

from bluecore_models.utils.marc import replace_dlc_assigner
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from lxml import etree
from marc_bibframe import marc_to_marcxml, marcxml_to_graph
from rdflib import Graph

from bluecore_api.app.utils.examples import MARCXML_EXAMPLE
from bluecore_api.constants import READ_ONLY_ROLES, KeycloakRole
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)

endpoints = APIRouter()

#: Raw request bodies each route accepts, besides a multipart upload. These feed
#: both the runtime Content-Type check and the requestBody in the generated
#: OpenAPI, so the two cannot drift apart.
MARC2XML_RAW_TYPES = ("application/marc",)
MARC2BIBFRAME_RAW_TYPES = ("application/xml", "text/xml", "application/marc")

#: rdflib serializer name by response media type, in the order a client's Accept
#: header is matched against. The first entry is the default: what a missing
#: Accept header or `*/*` receives, and what this route returned before it
#: negotiated at all.
BIBFRAME_SERIALIZATIONS = {
    "application/ld+json": "json-ld",
    "application/rdf+xml": "xml",
    "text/turtle": "turtle",
    "application/n-triples": "nt",
}

#: Media types that resolve to the default serialization rather than naming one:
#: the wildcards, and application/json, which serializer_accept_registry in
#: app/utils/serializer.py also treats as a synonym for JSON-LD.
_DEFAULTED_ACCEPTS = frozenset({"", "*/*", "application/*", "application/json"})

DEFAULT_BIBFRAME_MEDIA_TYPE = next(iter(BIBFRAME_SERIALIZATIONS))

#: The source_base_uri of the bluecore-workflows `marc_to_bibframe` DAG, plus
#: the trailing slash the DAG omits. marc2bibframe2 joins the base and the
#: record id by plain concatenation, so a base without a trailing delimiter
#: mints `http://id.loc.gov/resources92005291#Work`.
DEFAULT_SOURCE_BASE_URI = "http://id.loc.gov/resources/"


def _delimited(source_base_uri: str) -> str:
    """Give the base URI a trailing delimiter, since the transform concatenates."""
    if source_base_uri.endswith(("/", "#", ":")):
        return source_base_uri
    return source_base_uri + "/"


def _negotiate(accept_header: str) -> str:
    """Pick a response media type from the Accept header.

    Follows app/utils/serializer.serialize(): media types are tried in the order
    the client listed them and `q=` parameters are stripped rather than ranked.
    A missing header, an empty one, or a wildcard gets JSON-LD, so clients that
    predate this negotiation keep the response they already handle. An Accept
    naming only things we cannot produce is a 406.
    """
    for accept_raw in accept_header.split(","):
        accept = accept_raw.split(";")[0].strip()
        if accept in _DEFAULTED_ACCEPTS:
            return DEFAULT_BIBFRAME_MEDIA_TYPE
        if accept in BIBFRAME_SERIALIZATIONS:
            return accept
    raise HTTPException(
        status_code=406,
        detail=(
            "Cannot serialize BIBFRAME as any of the requested media types. "
            f"Available: {', '.join(BIBFRAME_SERIALIZATIONS)}."
        ),
    )


def _marcxml_to_bibframe_graph(marcxml_bytes: bytes, source_base_uri: str) -> Graph:
    """Convert MARCXML to Blue Core BIBFRAME.

    marc-bibframe does the conversion; replace_dlc_assigner then applies the one
    piece of Blue Core policy that MARC-derived BIBFRAME needs. Given the same
    source_base_uri, this endpoint and the bluecore-workflows marc2bf DAG
    produce the same thing -- the DAG applies the same rewrite to the same
    transform's output.
    """
    graph = marcxml_to_graph(marcxml_bytes, baseuri=source_base_uri)
    replace_dlc_assigner(graph)
    return graph


def _detail_response(description: str, example: str) -> dict[str, object]:
    """Document an HTTPException body: {"detail": "..."} as application/json.

    FastAPI documents a 422 as its own HTTPValidationError, a list of per-field
    errors. Nothing on these routes raises that -- every 4xx here is an
    HTTPException with a string detail -- so the real shape is declared by hand.
    The same shape is spelled out for 401/403 in app/main.py; promote this to a
    shared helper if a third route module needs it.
    """
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {"detail": {"type": "string"}},
                },
                "example": {"detail": example},
            }
        },
    }


#: Request body schema per raw media type. OpenAPI 3.1, which this app emits,
#: has no `format: binary`; a byte payload is a string with a contentMediaType.
_RAW_BODY_SCHEMAS: dict[str, dict[str, object]] = {
    "application/marc": {
        "schema": {"type": "string", "contentMediaType": "application/marc"}
    },
    "application/xml": {"schema": {"type": "string"}, "example": MARCXML_EXAMPLE},
    "text/xml": {"schema": {"type": "string"}, "example": MARCXML_EXAMPLE},
}


def _raw_body_openapi(
    media_types: tuple[str, ...], description: str
) -> dict[str, object]:
    """Document the raw request bodies these routes accept.

    They read the request themselves so a raw body works as well as a multipart
    upload, which leaves FastAPI able to see only the multipart 'file' field.
    openapi_extra is deep-merged into the finished operation (see
    fastapi.utils.deep_dict_update), so naming the raw types here adds them
    alongside the generated multipart entry rather than replacing it.

    Order matters twice over: Swagger UI defaults to the first media type, and
    fastapi-mcp derives a tool's body arguments from the first one alone. Both
    want multipart, and because the merge appends, multipart stays first. Do not
    hoist a raw type to the front -- a `{"type": "string"}` body has no
    properties, so the MCP tool would lose its only payload argument.
    """
    return {
        "requestBody": {
            "required": True,
            "description": description,
            "content": {
                media_type: _RAW_BODY_SCHEMAS[media_type] for media_type in media_types
            },
        }
    }


MARC2XML_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "description": (
            "MARCXML: a `<collection>` holding one `<record>` per input record."
        ),
        "content": {"application/xml": {"schema": {"type": "string"}}},
    },
    415: _detail_response(
        "Body was neither a multipart upload with a `file` field nor a raw body "
        "with `Content-Type: application/marc`.",
        "Send multipart/form-data with a 'file' field or a raw body with "
        "Content-Type: application/marc.",
    ),
    422: _detail_response(
        "Body was empty, or could not be parsed as binary MARC21.",
        "Empty MARC payload.",
    ),
}

MARC2BIBFRAME_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "description": (
            "BIBFRAME in the serialization named by the `Accept` header. "
            "`application/ld+json` is the default, and is what a missing header "
            "or `*/*` receives."
        ),
        "content": {
            # rdflib's JSON-LD is a flat array of node objects, not one object.
            "application/ld+json": {
                "schema": {"type": "array", "items": {"type": "object"}}
            },
            "application/rdf+xml": {"schema": {"type": "string"}},
            "text/turtle": {"schema": {"type": "string"}},
            "application/n-triples": {"schema": {"type": "string"}},
        },
    },
    406: _detail_response(
        "`Accept` named no serialization this endpoint can produce.",
        "Cannot serialize BIBFRAME as any of the requested media types.",
    ),
    415: _detail_response(
        "Body was neither a multipart upload with a `file` field nor a raw body "
        "with `Content-Type: application/xml`, `text/xml`, or `application/marc`.",
        "Send multipart/form-data with a 'file' field, or a raw body with "
        "Content-Type: application/xml, text/xml, or application/marc.",
    ),
    422: _detail_response(
        "Body was empty, was not well-formed XML, or the BIBFRAME "
        "transformation failed.",
        "Empty payload.",
    ),
}


@endpoints.post(
    "/marc2xml",
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    operation_id="marc2xml",
    summary="Convert binary MARC21 to MARCXML",
    response_class=Response,
    responses=MARC2XML_RESPONSES,
    openapi_extra=_raw_body_openapi(
        MARC2XML_RAW_TYPES,
        "One or more binary MARC21 records, as a multipart `file` field or as "
        "the raw body.",
    ),
)
async def marc2xml(
    request: Request,
    file: UploadFile = File(None),
):
    """
    Convert a binary MARC file to MARCXML.

    Accepts either:
    - Multipart form-data with a ``file`` field containing binary MARC data.
    - A raw binary body with ``Content-Type: application/marc``.

    Returns MARCXML as ``application/xml``.
    """
    if file and getattr(file, "filename", None):
        marc_bytes = await file.read()
    else:
        ct = (request.headers.get("content-type") or "").lower()
        if not ct.startswith(MARC2XML_RAW_TYPES):
            raise HTTPException(
                status_code=415,
                detail="Send multipart/form-data with a 'file' field or a raw body with Content-Type: application/marc.",
            )
        marc_bytes = await request.body()

    if not marc_bytes:
        raise HTTPException(status_code=422, detail="Empty MARC payload.")

    try:
        marcxml_bytes = marc_to_marcxml(marc_bytes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to parse MARC data: {exc}")

    return Response(content=marcxml_bytes, media_type="application/xml")


@endpoints.post(
    "/marc2bibframe",
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    operation_id="marc2bibframe",
    summary="Convert MARC or MARCXML to Blue Core BIBFRAME",
    response_class=Response,
    responses=MARC2BIBFRAME_RESPONSES,
    openapi_extra=_raw_body_openapi(
        MARC2BIBFRAME_RAW_TYPES,
        "MARCXML, or one or more binary MARC21 records, as a multipart `file` "
        "field or as the raw body.",
    ),
)
async def marc2bibframe(
    request: Request,
    file: UploadFile = File(None),
    source_base_uri: Annotated[
        str,
        Query(
            description=(
                "Base for the URIs the transform mints. Minted URIs have the "
                "form `{source_base_uri}{record id}#{fragment}`, so they are "
                "scoped to the record they came from and are **not** authority "
                "URIs: two records describing the same person yield two "
                "different agent URIs. A trailing slash is added if missing. "
                "Named to match the `source_base_uri` parameter of the "
                "bluecore-workflows `marc_to_bibframe` DAG, and defaulting to "
                "the same value."
            ),
            examples=["https://bcld.info/"],
        ),
    ] = DEFAULT_SOURCE_BASE_URI,
):
    """
    Convert MARC to Blue Core BIBFRAME, with Blue Core policy applied.

    The conversion is the Library of Congress marc2bibframe2 stylesheet, via
    the marc-bibframe package, run in this process -- no Airflow involved. Blue
    Core then names CBC rather than DLC as the assigner of identifiers derived
    from the record.

    Accepts either:
    - Multipart form-data with a ``file`` field containing MARCXML or binary MARC21.
    - A raw body with ``Content-Type: application/xml``, ``text/xml``,
      or ``application/marc``.

    Binary MARC21 payloads are automatically converted to MARCXML before
    the BIBFRAME transformation. ``source_base_uri`` applies to both request
    shapes.

    The response serialization is chosen by the ``Accept`` header: JSON-LD (the
    default), RDF/XML, turtle, or N-Triples.
    """
    media_type = _negotiate(request.headers.get("accept", ""))

    if file and getattr(file, "filename", None):
        raw_bytes = await file.read()
    else:
        ct = (request.headers.get("content-type") or "").lower()
        if not ct.startswith(MARC2BIBFRAME_RAW_TYPES):
            raise HTTPException(
                status_code=415,
                detail=(
                    "Send multipart/form-data with a 'file' field, "
                    "or a raw body with Content-Type: application/xml, text/xml, "
                    "or application/marc."
                ),
            )
        raw_bytes = await request.body()

    if not raw_bytes:
        raise HTTPException(status_code=422, detail="Empty payload.")

    # If the payload looks like binary MARC21 (not XML), convert to MARCXML first.
    if not raw_bytes.lstrip().startswith(b"<"):
        try:
            raw_bytes = marc_to_marcxml(raw_bytes)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=422, detail=f"Failed to parse MARC data: {exc}"
            )

    try:
        graph = _marcxml_to_bibframe_graph(raw_bytes, _delimited(source_base_uri))
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid XML: {exc}")
    except etree.XSLTApplyError as exc:
        raise HTTPException(status_code=422, detail=f"Transformation failed: {exc}")

    serialized = graph.serialize(format=BIBFRAME_SERIALIZATIONS[media_type])
    return Response(content=serialized, media_type=media_type)
