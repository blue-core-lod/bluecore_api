from pathlib import Path
from uuid import uuid4

import rdflib
from bluecore_models.models.version import CURRENT_USER_ID
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from bluecore_api import workflow
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


#: Uploads read as binary MARC21. resource_loader parses JSON-LD only, so
#: passing MARC through returned a 200 and a workflow id for a run that was
#: certain to fail. They are refused until bluecore-workflows has a bulk MARC
#: loader DAG to hand them to (blue-core-lod/bluecore-workflows#238).
MARC_SUFFIXES = (".mrc", ".marc")
MARC_MEDIA_TYPE = "application/marc"


def _is_marc_upload(filename: str, content_type: str | None) -> bool:
    """An upload is MARC if its name or its declared type says so."""
    if (content_type or "").lower().startswith(MARC_MEDIA_TYPE):
        return True
    return filename.lower().endswith(MARC_SUFFIXES)


def _refuse_marc() -> HTTPException:
    return HTTPException(
        status_code=415,
        detail=(
            "Bulk MARC loading is not supported yet. Use POST /marc2bibframe "
            "to convert a single record."
        ),
    )


def _xml_to_jsonld_and_save(
    upload_root: Path, xml_data: bytes | str, name: str | None = None
) -> str:
    """
    Convert RDF/XML (bytes or str) to JSON-LD, save under ./uploads/<uuid>/<name>.jsonld,
    and return the /opt/airflow/uploads/... file_location string.
    """
    g = rdflib.Graph()
    g.parse(data=xml_data, format="xml")
    jsonld_text = g.serialize(format="json-ld")

    safe_name = (name or "batch").rsplit(".", 1)[0]
    batch_file = f"{uuid4()}/{safe_name}.jsonld"

    batch_path = upload_root / batch_file
    batch_path.parent.mkdir(parents=True, exist_ok=True)
    batch_path.write_text(jsonld_text)

    file_location = f"/opt/airflow/uploads/{batch_file}"
    return file_location


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
):
    """
    Multipart with 'file' -> save as-is.
    Otherwise:
      - binary MARC (a .mrc or .marc file, or application/marc) -> 415, until
        bluecore-workflows has a bulk MARC loader to hand it to
      - application/json body: {"name": "...", "rdfxml": "..."} -> XML -> JSON-LD
      - application/xml or text/xml raw body -> XML -> JSON-LD
    Then trigger the Airflow DAG using the saved path.
    """
    user_uid = CURRENT_USER_ID.get()

    try:
        upload_root = Path("./uploads")
        upload_root.mkdir(parents=True, exist_ok=True)

        ct = (request.headers.get("content-type") or "").lower()
        has_file = bool(file and getattr(file, "filename", None))

        if (has_file and _is_marc_upload(file.filename or "", file.content_type)) or (
            not has_file and ct.startswith(MARC_MEDIA_TYPE)
        ):
            raise _refuse_marc()

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

            file_location = _xml_to_jsonld_and_save(upload_root, xml_bytes)
            workflow_id = await workflow.create_batch_from_uri(
                file_location, user_uid=user_uid
            )
            return {"uri": file_location, "workflow_id": workflow_id}

        # Otherwise: unsupported
        raise HTTPException(
            status_code=415,
            detail=(
                "Send multipart/form-data with a file, application/json with 'rdfxml', or application/xml."
            ),
        )

    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))
