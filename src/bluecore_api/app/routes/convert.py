"""Convert MARC records to MARCXML and to Blue Core BIBFRAME.

These routes convert one record per request. They hold the whole request and
the whole response in memory and answer synchronously on the event loop, and
production runs a single uvicorn worker, so an unbounded request would stall
every other request to the API for as long as its transform took. Load testing
with real Library of Congress records measured 11 ms for one record and 9.5 s of
full-API stall for a thousand, hence the two guards here: a body larger than
MAX_CONVERT_BYTES or carrying more than one record is refused with a 413.

Bulk MARC belongs in a batch workflow: today that means the bluecore-workflows
`marc_to_bibframe` DAG with `ingest=true`, since `/batches/upload/` hands its
uploads to `resource_loader`, which reads JSON-LD rather than MARC.
"""

from copy import deepcopy
from io import BytesIO
from typing import Annotated
from urllib.parse import urlparse

import pymarc
from bluecore_models.utils.marc import replace_dlc_assigner
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from lxml import etree
from marc_bibframe import (
    DEFAULT_BASE_URI,
    marc_to_marcxml,
    marcxml_to_graph,
)
from pymarc.exceptions import PymarcException
from rdflib import Graph

from bluecore_api.app.utils.examples import MARCXML_EXAMPLE
from bluecore_api.app.utils.serializer import accept_media_types
from bluecore_api.constants import MAX_CONVERT_BYTES, READ_ONLY_ROLES, KeycloakRole
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
#: the catch-all wildcards, and application/json, which
#: serializer_accept_registry in app/utils/serializer.py also treats as a
#: synonym for JSON-LD.
_DEFAULTED_ACCEPTS = frozenset({"", "*", "*/*", "application/json"})

DEFAULT_BIBFRAME_MEDIA_TYPE = next(iter(BIBFRAME_SERIALIZATIONS))

#: marc-bibframe's own default, and deliberately non-resolvable: the URIs the
#: transform mints name nothing, so a caller who does not pass a base should get
#: URIs that are obviously placeholders rather than ones that look like an
#: authority's. The bluecore-workflows `marc_to_bibframe` DAG defaults to
#: `http://id.loc.gov/resources` instead, which mints fabricated URIs inside
#: id.loc.gov (and, lacking a trailing slash, malformed ones).
DEFAULT_SOURCE_BASE_URI = DEFAULT_BASE_URI


#: Characters rdflib refuses to serialize in a URI (rdflib.term._invalid_uri_chars
#: plus the controls), mirrored here so we reject them up front. Left to
#: rdflib they surface as a bare Exception during serialization -- a 500 for
#: turtle and N-Triples, and for JSON-LD a 200 carrying malformed URIs.
_INVALID_URI_CHARS = frozenset('<>" {}|\\^`') | {chr(c) for c in range(33)}


def _base_uri(source_base_uri: str) -> str:
    """Validate the base URI, and give it a trailing slash.

    The transform concatenates the base, the record id and "#fragment", so an
    unchecked value yields URIs that are wrong rather than an error: an empty
    base mints a relative "/92005291#Work", and a space in the base mints
    something rdflib will not serialize.
    """
    parsed = urlparse(source_base_uri)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"source_base_uri must be an http(s) URI with a host; "
                f"got {source_base_uri!r}."
            ),
        )
    if bad := sorted(_INVALID_URI_CHARS.intersection(source_base_uri)):
        raise HTTPException(
            status_code=422,
            detail=(
                f"source_base_uri contains characters that cannot appear in a "
                f"URI: {''.join(bad)!r}."
            ),
        )
    if "#" in source_base_uri:
        # The transform appends its own "#fragment", so a base carrying one
        # mints http://example.edu/rec#92005291#Work -- two fragments, which
        # RFC 3986 forbids and which rdflib serializes without complaint.
        raise HTTPException(
            status_code=422,
            detail="source_base_uri must not contain a fragment.",
        )
    if source_base_uri.endswith("/"):
        return source_base_uri
    return source_base_uri + "/"


#: Windows tools prepend this to UTF-8 text: Notepad, Excel's "CSV UTF-8", and
#: anything using .NET's default UTF-8 encoding. It is invisible in an editor,
#: and bytes.lstrip() does not remove it (that strips ASCII whitespace only), so
#: it would defeat the "does this start with '<'" sniff and send a perfectly
#: good MARCXML file down the binary MARC path.
_UTF8_BOM = b"\xef\xbb\xbf"


def _check_declared_size(request: Request) -> None:
    """Refuse an oversized raw body by its Content-Length, before reading it.

    Only called on the raw-body path. On a multipart upload FastAPI has already
    parsed and spooled the whole request before the handler's first statement,
    so checking there would buy nothing and would measure the multipart
    envelope rather than the record, rejecting a file the part-size check would
    accept. A limit that bites ahead of body parsing belongs in middleware or
    in nginx's client_max_body_size.

    Content-Length is absent under chunked transfer-encoding, which is why
    _check_size() checks again once the bytes are in hand.
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_CONVERT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Body is {declared} bytes; this endpoint converts one record "
                f"and reads at most {MAX_CONVERT_BYTES}."
            ),
        )


def _check_size(raw_bytes: bytes) -> None:
    """Refuse an oversized body once read, covering a missing Content-Length."""
    if len(raw_bytes) > MAX_CONVERT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Body is {len(raw_bytes)} bytes; this endpoint converts one "
                f"record and reads at most {MAX_CONVERT_BYTES}."
            ),
        )


def _too_many_records(count: int) -> HTTPException:
    """The one place the batch refusal is worded, raised from both checks."""
    return HTTPException(
        status_code=413,
        detail=(
            f"Received {count} records; this endpoint converts one. Bulk "
            "MARC belongs in a batch workflow."
        ),
    )


def _reject_obvious_batch(marc_bytes: bytes) -> None:
    """Refuse binary MARC carrying several records, before converting them.

    pymarc reads the records without building MARCXML, which at the byte cap is
    ~22 ms against ~90 ms for the conversion this saves. Counting record
    terminator bytes would be faster still, but 0x1D can appear in subfield
    data, and that reads a single record as a batch and refuses it.

    Advisory: unreadable input counts as nothing here and is reported properly
    by marc_to_marcxml a moment later.
    """
    try:
        # MARCReader yields None for a record it cannot read, which is how
        # marc_to_marcxml detects bad input too.
        count = sum(1 for record in pymarc.MARCReader(BytesIO(marc_bytes)) if record)
    except (PymarcException, ValueError):
        return  # marc_to_marcxml reports it as a 422 a moment later
    if count > 1:
        raise _too_many_records(count)


#: MARCXML's namespace. Checked as well as the element name, because the
#: transform only recognises records in it: without this an OAI-PMH <record>,
#: or a namespace-less one, passes the guard and returns 200 with an empty graph.
MARCXML_NAMESPACE = "http://www.loc.gov/MARC21/slim"


def _is_marc_record(element: etree._Element) -> bool:
    name = etree.QName(element)
    return name.localname == "record" and name.namespace == MARCXML_NAMESPACE


def _require_single_record(marcxml: bytes) -> None:
    """Refuse a MARCXML collection holding anything but one record.

    Counted on the parsed XML rather than by scanning bytes for b"<record",
    which would miss a namespace-prefixed <marc:record> and would count
    <recordset>. The parse costs well under 1% of the transform it guards.

    iter("*") rather than iter(): the latter also yields comments and
    processing instructions, and QName() raises on those. ILS exports routinely
    carry a comment.
    """
    root = etree.fromstring(marcxml)
    if _is_marc_record(root):
        return  # a bare <record>, not wrapped in a <collection>
    count = sum(1 for el in root.iter("*") if _is_marc_record(el))
    if count == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "No MARC record found. Records must be <record> elements in the "
                f"{MARCXML_NAMESPACE} namespace."
            ),
        )
    if count > 1:
        raise _too_many_records(count)


def _negotiate(accept_header: str) -> str:
    """Pick a response media type from the Accept header.

    accept_media_types() does the parsing, shared with the resource routes, so
    the client's ordering decides here too. A missing header, an empty one, or a
    wildcard gets JSON-LD, so clients that predate this negotiation keep the
    response they already handle. An Accept naming only things we cannot produce
    is a 406, where the resource routes would fall back to HTML.
    """
    for accept in accept_media_types(accept_header):
        if accept in _DEFAULTED_ACCEPTS:
            return DEFAULT_BIBFRAME_MEDIA_TYPE
        if accept in BIBFRAME_SERIALIZATIONS:
            return accept
        if accept.endswith("/*"):
            # A subtype wildcard takes the first thing we offer of that type,
            # so text/* gets turtle and application/* gets JSON-LD.
            offered = accept[: -len("*")]
            for media_type in BIBFRAME_SERIALIZATIONS:
                if media_type.startswith(offered):
                    return media_type
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
            # Deep-copied because FastAPI deep-copies route.responses but merges
            # openapi_extra by reference, so both operations and this module
            # constant would otherwise share one mutable dict.
            "content": {
                media_type: deepcopy(_RAW_BODY_SCHEMAS[media_type])
                for media_type in media_types
            },
        }
    }


MARC2XML_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "description": ("MARCXML: a `<collection>` holding the converted `<record>`."),
        "content": {"application/xml": {"schema": {"type": "string"}}},
    },
    413: _detail_response(
        "Body exceeded the byte limit, or carried more than one record.",
        "Received 2 records; this endpoint converts one. Bulk MARC belongs in a "
        "batch workflow.",
    ),
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
    413: _detail_response(
        "Body exceeded the byte limit, or carried more than one record.",
        "Received 2 records; this endpoint converts one. Bulk MARC belongs in a "
        "batch workflow.",
    ),
    415: _detail_response(
        "Body was neither a multipart upload with a `file` field nor a raw body "
        "with `Content-Type: application/xml`, `text/xml`, or `application/marc`.",
        "Send multipart/form-data with a 'file' field, or a raw body with "
        "Content-Type: application/xml, text/xml, or application/marc.",
    ),
    422: _detail_response(
        "Body was empty, held no record, was not well-formed XML, or the "
        "BIBFRAME transformation failed; or `source_base_uri` was not an "
        "http(s) URI.",
        "No MARC record found.",
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
        "A single binary MARC21 record, as a multipart `file` field or as the "
        "raw body.",
    ),
)
async def marc2xml(
    request: Request,
    file: UploadFile = File(None),
):
    """
    Convert a binary MARC record to MARCXML.

    One record per request. A body over the byte limit, or holding more than one
    record, is refused with a 413; bulk MARC belongs in a batch workflow.

    Accepts either:
    - Multipart form-data with a ``file`` field containing binary MARC data.
    - A raw binary body with ``Content-Type: application/marc``.

    Returns MARCXML as ``application/xml``.
    """
    if file and getattr(file, "filename", None):
        marc_bytes = await file.read()
    else:
        _check_declared_size(request)
        ct = (request.headers.get("content-type") or "").lower()
        if not ct.startswith(MARC2XML_RAW_TYPES):
            raise HTTPException(
                status_code=415,
                detail="Send multipart/form-data with a 'file' field or a raw body with Content-Type: application/marc.",
            )
        marc_bytes = await request.body()

    _check_size(marc_bytes)

    if not marc_bytes:
        raise HTTPException(status_code=422, detail="Empty MARC payload.")

    _reject_obvious_batch(marc_bytes)

    try:
        marcxml_bytes = marc_to_marcxml(marc_bytes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to parse MARC data: {exc}")

    try:
        # marc_to_marcxml copies subfield data through verbatim, so a control
        # character in the record makes this parse fail. marc2bibframe catches
        # the same thing where it parses.
        _require_single_record(marcxml_bytes)
    except etree.XMLSyntaxError as exc:
        raise HTTPException(
            status_code=422, detail=f"MARC data produced invalid XML: {exc}"
        )

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
        "A single record as MARCXML or as binary MARC21, in a multipart `file` "
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

    One record per request. A body over the byte limit, or holding more than one
    record, is refused with a 413; bulk MARC belongs in a batch workflow.

    Binary MARC21 payloads are converted to MARCXML before the BIBFRAME
    transformation. A leading UTF-8 byte order mark is ignored, so MARCXML saved
    by a Windows editor is read as XML rather than as MARC.
    ``source_base_uri`` applies to both request shapes.

    The response serialization is chosen by the ``Accept`` header: JSON-LD (the
    default), RDF/XML, turtle, or N-Triples.
    """
    media_type = _negotiate(request.headers.get("accept", ""))
    base_uri = _base_uri(source_base_uri)

    if file and getattr(file, "filename", None):
        raw_bytes = await file.read()
    else:
        _check_declared_size(request)
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

    _check_size(raw_bytes)

    if not raw_bytes:
        raise HTTPException(status_code=422, detail="Empty payload.")

    raw_bytes = raw_bytes.removeprefix(_UTF8_BOM)

    # If the payload looks like binary MARC21 (not XML), convert to MARCXML first.
    if not raw_bytes.lstrip().startswith(b"<"):
        _reject_obvious_batch(raw_bytes)
        try:
            raw_bytes = marc_to_marcxml(raw_bytes)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=422, detail=f"Failed to parse MARC data: {exc}"
            )

    try:
        # Both parse the MARCXML, so one XMLSyntaxError handler covers them. The
        # 413 that _require_single_record raises is an HTTPException and passes
        # through, which is what keeps the transform from running on a rejected
        # request.
        _require_single_record(raw_bytes)
        graph = _marcxml_to_bibframe_graph(raw_bytes, base_uri)
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid XML: {exc}")
    except etree.XSLTApplyError as exc:
        raise HTTPException(status_code=422, detail=f"Transformation failed: {exc}")

    serialized = graph.serialize(format=BIBFRAME_SERIALIZATIONS[media_type])
    return Response(content=serialized, media_type=media_type)
