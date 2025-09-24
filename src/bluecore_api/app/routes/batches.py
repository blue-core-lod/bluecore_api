from pathlib import Path
from uuid import uuid4

import rdflib
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi_keycloak_middleware import CheckPermissions

from bluecore_api import workflow
from bluecore_api.schemas.schemas import BatchCreateSchema, BatchSchema

endpoints = APIRouter()


@endpoints.post(
    "/batches/",
    response_model=BatchSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
)
async def create_batch(batch: BatchCreateSchema):
    """Create a batch from a URI (unchanged behavior)."""
    try:
        workflow_id = await workflow.create_batch_from_uri(batch.uri)
    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"uri": batch.uri, "workflow_id": workflow_id}


@endpoints.post(
    "/batches/upload/",
    response_model=BatchSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
)
async def create_batch_file(
    request: Request,
    file: UploadFile = File(None),
):
    """
    Multipart with 'file' -> save as-is.
    Otherwise:
      - application/json body: {"name": "...", "rdfxml": "..."} -> XML -> JSON-LD
      - application/xml or text/xml raw body -> XML -> JSON-LD
    Then trigger the Airflow DAG using the saved path.
    """
    try:
        upload_root = Path("./uploads")
        upload_root.mkdir(parents=True, exist_ok=True)

        # Case A: multipart file present -> PASS THROUGH (legacy)
        if file and getattr(file, "filename", None):
            batch_file = f"{uuid4()}/{file.filename}"
            batch_path = upload_root / batch_file
            batch_path.parent.mkdir(parents=True, exist_ok=True)

            with batch_path.open("wb") as fh:
                while chunk := file.file.read(1024 * 1024):
                    fh.write(chunk)

            file_location = f"/opt/airflow/uploads/{batch_file}"
            workflow_id = await workflow.create_batch_from_uri(file_location)
            return {"uri": file_location, "workflow_id": workflow_id}

        # No multipart file: inspect content-type
        ct = (request.headers.get("content-type") or "").lower()

        # Case B: JSON body with rdfxml -> convert to JSON-LD
        if ct.startswith("application/json"):
            data = await request.json()
            rdfxml = data.get("rdfxml")
            if not isinstance(rdfxml, str) or not rdfxml.strip():
                raise HTTPException(
                    status_code=422, detail="Provide 'rdfxml' in the JSON body."
                )
            name = (data.get("name") or "batch").rsplit(".", 1)[0]

            g = rdflib.Graph()
            g.parse(data=rdfxml, format="xml")
            jsonld_text = g.serialize(format="json-ld")

            batch_file = f"{uuid4()}/{name}.jsonld"
            batch_path = upload_root / batch_file
            batch_path.parent.mkdir(parents=True, exist_ok=True)
            batch_path.write_text(jsonld_text)

            file_location = f"/opt/airflow/uploads/{batch_file}"
            workflow_id = await workflow.create_batch_from_uri(file_location)
            return {"uri": file_location, "workflow_id": workflow_id}

        # Case C: raw XML body -> convert to JSON-LD
        if ct.startswith("application/xml") or ct.startswith("text/xml"):
            xml_bytes = await request.body()
            if not xml_bytes:
                raise HTTPException(status_code=422, detail="Empty XML body.")

            g = rdflib.Graph()
            g.parse(data=xml_bytes, format="xml")
            jsonld_text = g.serialize(format="json-ld")

            batch_file = f"{uuid4()}/batch.jsonld"
            batch_path = upload_root / batch_file
            batch_path.parent.mkdir(parents=True, exist_ok=True)
            batch_path.write_text(jsonld_text)

            file_location = f"/opt/airflow/uploads/{batch_file}"
            workflow_id = await workflow.create_batch_from_uri(file_location)
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
