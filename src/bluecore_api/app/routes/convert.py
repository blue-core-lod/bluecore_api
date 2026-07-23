from importlib.resources import files
from io import BytesIO

import rdflib
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from lxml import etree
from pymarc import MARCReader
from pymarc.marcxml import record_to_xml

from bluecore_api.constants import READ_ONLY_ROLES, KeycloakRole
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)

endpoints = APIRouter()

_COLLECTION_OPEN = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<collection xmlns="http://www.loc.gov/MARC21/slim">'
)
_COLLECTION_CLOSE = b"</collection>"

# Compile the LC marc2bibframe2 XSLT once at import time.
_XSL_PATH = files("bluecore_api").joinpath("xsl/marc2bibframe2.xsl")
_MARC2BF_TRANSFORM = etree.XSLT(etree.parse(str(_XSL_PATH)))


def _marc_bytes_to_marcxml(marc_bytes: bytes) -> bytes:
    """Convert raw binary MARC bytes to MARCXML bytes."""
    parts = [_COLLECTION_OPEN]
    reader = MARCReader(BytesIO(marc_bytes))
    for record in reader:
        parts.append(record_to_xml(record, namespace=False))
    parts.append(_COLLECTION_CLOSE)
    return b"".join(parts)


def _marcxml_to_bibframe_jsonld(marcxml_bytes: bytes) -> str:
    """Apply the LC marc2bibframe2 XSLT to MARCXML and return BIBFRAME as JSON-LD."""
    doc = etree.fromstring(marcxml_bytes)
    rdfxml_bytes = etree.tostring(_MARC2BF_TRANSFORM(doc))
    g = rdflib.Graph()
    g.parse(data=rdfxml_bytes, format="xml")
    return g.serialize(format="json-ld")


@endpoints.post(
    "/marc2xml",
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    operation_id="marc2xml",
    response_class=Response,
    responses={200: {"content": {"application/xml": {}}}},
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
        if not ct.startswith("application/marc"):
            raise HTTPException(
                status_code=415,
                detail="Send multipart/form-data with a 'file' field or a raw body with Content-Type: application/marc.",
            )
        marc_bytes = await request.body()

    if not marc_bytes:
        raise HTTPException(status_code=422, detail="Empty MARC payload.")

    try:
        marcxml_bytes = _marc_bytes_to_marcxml(marc_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse MARC data: {exc}")

    return Response(content=marcxml_bytes, media_type="application/xml")


@endpoints.post(
    "/marc2bibframe",
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    operation_id="marc2bibframe",
    response_class=Response,
    responses={200: {"content": {"application/ld+json": {}}}},
)
async def marc2bibframe(
    request: Request,
    file: UploadFile = File(None),
):
    """
    Convert MARCXML to BIBFRAME JSON-LD using the LC marc2bibframe2 stylesheet.

    Accepts either:
    - Multipart form-data with a ``file`` field containing MARCXML.
    - A raw body with ``Content-Type: application/xml`` or ``Content-Type: text/xml``.

    Returns BIBFRAME as ``application/ld+json``.
    """
    if file and getattr(file, "filename", None):
        marcxml_bytes = await file.read()
    else:
        ct = (request.headers.get("content-type") or "").lower()
        if not (ct.startswith("application/xml") or ct.startswith("text/xml")):
            raise HTTPException(
                status_code=415,
                detail=(
                    "Send multipart/form-data with a 'file' field, "
                    "or a raw body with Content-Type: application/xml or text/xml."
                ),
            )
        marcxml_bytes = await request.body()

    if not marcxml_bytes:
        raise HTTPException(status_code=422, detail="Empty MARCXML payload.")

    try:
        jsonld = _marcxml_to_bibframe_jsonld(marcxml_bytes)
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid XML: {exc}")
    except etree.XSLTApplyError as exc:
        raise HTTPException(status_code=422, detail=f"Transformation failed: {exc}")

    return Response(content=jsonld, media_type="application/ld+json")
