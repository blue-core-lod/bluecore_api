from pathlib import Path
from typing import Annotated
from uuid import uuid4

import rdflib
from bluecore_models.models.version import CURRENT_USER_ID
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from lxml import etree
from marc_bibframe import marc_to_marcxml

from bluecore_api import workflow
from bluecore_api.app.routes.convert import (
    DEFAULT_SOURCE_BASE_URI,
    MARCXML_NAMESPACE,
    marcxml_to_bibframe_graph,
    normalize_base_uri,
)
from bluecore_api.constants import READ_ONLY_ROLES, KeycloakRole
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)
from bluecore_api.schemas.schemas import BatchCreateSchema, BatchSchema

endpoints = APIRouter()

# File extensions that indicate an archive of RDF files to be bulk loaded via
# the archived_file_loader DAG rather than the single-file resource_loader DAG.
ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".gz")


def _dag_for_filename(filename: str) -> str:
    """Pick the Airflow DAG based on whether the upload is an archive."""
    lower = filename.lower()
    if any(lower.endswith(suffix) for suffix in ARCHIVE_SUFFIXES):
        return "archived_file_loader"
    return "resource_loader"


#: Uploads read as binary MARC21 and converted to JSON-LD before resource_loader
#: sees them: that DAG parses JSON-LD only, so passing MARC through returned a
#: 200 and a workflow id for a run that was certain to fail. The suffixes match
#: what the bluecore-workflows marc_to_bibframe DAG treats as binary MARC,
#: except .dat, which is too generic to claim.
MARC_SUFFIXES = (".mrc", ".marc")
MARC_MEDIA_TYPE = "application/marc"

_UTF8_BOM = b"\xef\xbb\xbf"


def _is_marc_upload(filename: str, content_type: str | None) -> bool:
    """A multipart part is MARC if its name or its declared type says so."""
    if (content_type or "").lower().startswith(MARC_MEDIA_TYPE):
        return True
    return filename.lower().endswith(MARC_SUFFIXES)


def _is_marcxml(xml_bytes: bytes) -> bool:
    """True when the document element is in the MARCXML namespace.

    Distinguishes a MARCXML <collection> or <record> from RDF/XML on the raw
    XML path. XML that does not parse is left to the RDF/XML branch to report.
    """
    try:
        root = etree.fromstring(xml_bytes.removeprefix(_UTF8_BOM))
    except etree.XMLSyntaxError:
        return False
    return etree.QName(root).namespace == MARCXML_NAMESPACE


def _marc_to_jsonld(marc_bytes: bytes, base_uri: str) -> str:
    """Convert binary MARC21 or MARCXML, any number of records, to JSON-LD.

    The same marcxml_to_bibframe_graph() as POST /marc2bibframe, so a record
    ingested here matches what that endpoint returns for it. CPU-bound and
    unbounded in the number of records, so callers run it in the threadpool
    rather than on the event loop (see #350).
    """
    marc_bytes = marc_bytes.removeprefix(_UTF8_BOM)
    if not marc_bytes.strip():
        raise HTTPException(status_code=422, detail="Empty MARC payload.")

    if not marc_bytes.lstrip().startswith(b"<"):
        try:
            marc_bytes = marc_to_marcxml(marc_bytes)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=422, detail=f"Failed to parse MARC data: {exc}"
            )

    try:
        graph = marcxml_to_bibframe_graph(marc_bytes, base_uri)
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid MARCXML: {exc}")
    except etree.XSLTApplyError as exc:
        raise HTTPException(status_code=422, detail=f"Transformation failed: {exc}")

    if len(graph) == 0:
        raise HTTPException(status_code=422, detail="No MARC records found to convert.")
    return graph.serialize(format="json-ld")


def _save_jsonld(upload_root: Path, jsonld_text: str, name: str | None) -> str:
    """Save JSON-LD under ./uploads/<uuid>/<name>.jsonld, return the Airflow path."""
    safe_name = (name or "batch").rsplit(".", 1)[0]
    batch_file = f"{uuid4()}/{safe_name}.jsonld"

    batch_path = upload_root / batch_file
    batch_path.parent.mkdir(parents=True, exist_ok=True)
    batch_path.write_text(jsonld_text)

    return f"/opt/airflow/uploads/{batch_file}"


def _xml_to_jsonld_and_save(
    upload_root: Path, xml_data: bytes | str, name: str | None = None
) -> str:
    """
    Convert RDF/XML (bytes or str) to JSON-LD, save under ./uploads/<uuid>/<name>.jsonld,
    and return the /opt/airflow/uploads/... file_location string.
    """
    g = rdflib.Graph()
    g.parse(data=xml_data, format="xml")
    return _save_jsonld(upload_root, g.serialize(format="json-ld"), name)


@endpoints.post(
    "/batches/",
    response_model=BatchSchema,
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    operation_id="create_batch",
)
async def create_batch(batch: BatchCreateSchema):
    """Create a batch from a URI (unchanged behavior)."""
    if not batch.uri:
        raise HTTPException(status_code=422, detail="uri is required")
    user_uid = CURRENT_USER_ID.get()  # => "anonymous" if no token
    try:
        workflow_id = await workflow.create_batch_from_uri(
            batch.uri,
            user_uid=user_uid,
        )
    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"uri": batch.uri, "workflow_id": workflow_id}


@endpoints.post(
    "/batches/upload/",
    response_model=BatchSchema,
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    operation_id="batch_upload",
)
async def create_batch_file(
    request: Request,
    file: UploadFile = File(None),
    source_base_uri: Annotated[
        str,
        Query(
            description=(
                "MARC uploads only: base for the URIs the MARC transform mints, "
                "as for `POST /marc2bibframe`. A trailing slash is added if "
                "missing."
            ),
            examples=["https://bcld.info/"],
        ),
    ] = DEFAULT_SOURCE_BASE_URI,
):
    """
    Multipart with 'file':
      - binary MARC21 (a .mrc or .marc file, or a part typed application/marc)
        -> BIBFRAME JSON-LD, any number of records
      - anything else -> save as-is
    Otherwise:
      - application/marc raw body -> BIBFRAME JSON-LD
      - application/json body: {"name": "...", "rdfxml": "..."} -> XML -> JSON-LD
      - application/xml or text/xml raw body -> JSON-LD, read as MARCXML when
        its document element is in the MARC21 namespace and as RDF/XML otherwise
    Then trigger the resource_loader Airflow DAG using the saved path (or
    archived_file_loader for an archive).

    MARC is converted here with the same transform as POST /marc2bibframe, and
    a MARC payload that cannot be read is a 422 rather than a DAG run that fails.
    """
    user_uid = CURRENT_USER_ID.get()

    try:
        upload_root = Path("./uploads")
        upload_root.mkdir(parents=True, exist_ok=True)

        # Case M: MARC, as a multipart part or a raw body -> BIBFRAME JSON-LD
        ct = (request.headers.get("content-type") or "").lower()
        has_file = bool(file and getattr(file, "filename", None))
        if (has_file and _is_marc_upload(file.filename or "", file.content_type)) or (
            not has_file and ct.startswith(MARC_MEDIA_TYPE)
        ):
            base_uri = normalize_base_uri(source_base_uri)
            marc_bytes = await (file.read() if has_file else request.body())
            name = file.filename if has_file else "batch"
            jsonld_text = await run_in_threadpool(_marc_to_jsonld, marc_bytes, base_uri)
            file_location = _save_jsonld(upload_root, jsonld_text, name)
            workflow_id = await workflow.create_batch_from_uri(
                file_location, user_uid=user_uid
            )
            return {"uri": file_location, "workflow_id": workflow_id}

        # Case A: multipart file present -> PASS THROUGH (legacy)
        if has_file:
            filename = file.filename or "upload"
            batch_file = f"{uuid4()}/{filename}"
            batch_path = upload_root / batch_file
            batch_path.parent.mkdir(parents=True, exist_ok=True)

            with batch_path.open("wb") as fh:
                while chunk := file.file.read(1024 * 1024):
                    fh.write(chunk)

            file_location = f"/opt/airflow/uploads/{batch_file}"
            workflow_id = await workflow.create_batch_from_uri(
                file_location,
                user_uid=user_uid,
                dag_id=_dag_for_filename(filename),
            )
            return {"uri": file_location, "workflow_id": workflow_id}

        # Case B: JSON body with rdfxml -> convert to JSON-LD
        if ct.startswith("application/json"):
            data = await request.json()
            rdfxml = data.get("rdfxml")
            if not isinstance(rdfxml, str) or not rdfxml.strip():
                raise HTTPException(
                    status_code=422, detail="Provide 'rdfxml' in the JSON body."
                )
            name = data.get("name") or "batch"

            file_location = _xml_to_jsonld_and_save(upload_root, rdfxml, name=name)
            workflow_id = await workflow.create_batch_from_uri(
                file_location, user_uid=user_uid
            )
            return {"uri": file_location, "workflow_id": workflow_id}

        # Case C: raw XML body -> convert to JSON-LD
        if ct.startswith(("application/xml", "text/xml")):
            xml_bytes = await request.body()
            if not xml_bytes:
                raise HTTPException(status_code=422, detail="Empty XML body.")

            if _is_marcxml(xml_bytes):
                base_uri = normalize_base_uri(source_base_uri)
                jsonld_text = await run_in_threadpool(
                    _marc_to_jsonld, xml_bytes, base_uri
                )
                file_location = _save_jsonld(upload_root, jsonld_text, None)
            else:
                file_location = _xml_to_jsonld_and_save(upload_root, xml_bytes)
            workflow_id = await workflow.create_batch_from_uri(
                file_location, user_uid=user_uid
            )
            return {"uri": file_location, "workflow_id": workflow_id}

        # Otherwise: unsupported
        raise HTTPException(
            status_code=415,
            detail=(
                "Send multipart/form-data with a file, application/json with "
                "'rdfxml', application/xml, or application/marc."
            ),
        )

    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))
