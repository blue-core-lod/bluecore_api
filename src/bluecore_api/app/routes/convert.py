from bluecore_models.utils.marc import replace_dlc_assigner
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from lxml import etree
from marc_bibframe import marc_to_marcxml, marcxml_to_graph

from bluecore_api.constants import READ_ONLY_ROLES, KeycloakRole
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)

endpoints = APIRouter()


def _marcxml_to_bibframe_jsonld(marcxml_bytes: bytes) -> str:
    """Convert MARCXML to Blue Core BIBFRAME as JSON-LD.

    marc-bibframe does the conversion; replace_dlc_assigner then applies the
    one piece of Blue Core policy that MARC-derived BIBFRAME needs, so this
    endpoint and the bluecore-workflows marc2bf DAG produce the same thing.
    """
    graph = marcxml_to_graph(marcxml_bytes)
    replace_dlc_assigner(graph)
    return graph.serialize(format="json-ld")


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
        marcxml_bytes = marc_to_marcxml(marc_bytes)
    except Exception as exc:  # noqa: BLE001
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
    Convert MARC to BIBFRAME JSON-LD, with Blue Core policy applied.

    The conversion is the Library of Congress marc2bibframe2 stylesheet, via
    the marc-bibframe package. Blue Core then names CBC rather than DLC as the
    assigner of identifiers derived from the record.

    Accepts either:
    - Multipart form-data with a ``file`` field containing MARCXML or binary MARC21.
    - A raw body with ``Content-Type: application/xml``, ``text/xml``,
      or ``application/marc``.

    Binary MARC21 payloads are automatically converted to MARCXML before
    the BIBFRAME transformation.

    Returns BIBFRAME as ``application/ld+json``.
    """
    if file and getattr(file, "filename", None):
        raw_bytes = await file.read()
    else:
        ct = (request.headers.get("content-type") or "").lower()
        if not ct.startswith(("application/xml", "text/xml", "application/marc")):
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
        jsonld = _marcxml_to_bibframe_jsonld(raw_bytes)
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid XML: {exc}")
    except etree.XSLTApplyError as exc:
        raise HTTPException(status_code=422, detail=f"Transformation failed: {exc}")

    return Response(content=jsonld, media_type="application/ld+json")
