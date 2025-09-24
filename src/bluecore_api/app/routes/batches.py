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
    """Authenticated route to create a batch from a URI."""
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
    Accepts either:
      1) multipart/form-data with a 'file' (supports .xml -> JSON-LD; .json/.jsonld passthrough)
      2) application/json body: {"name": "...", "rdfxml": "..."} (XML -> JSON-LD)
      3) raw XML body (application/xml or text/xml)
    Stores a .jsonld file and triggers the Airflow workflow.
    """
    try:
        upload_root = Path("./uploads")
        batch_dir = upload_root / f"{uuid4()}"
        batch_dir.mkdir(parents=True, exist_ok=True)

        ct = (request.headers.get("content-type") or "").lower()

        # ---- Case A: multipart file upload ----
        if file and getattr(file, "filename", None):
            raw = file.file.read()
            name = (file.filename or "batch").rsplit(".", 1)[0]
            fname_lower = (file.filename or "").lower()
            fct = (file.content_type or "").lower()

            if fct in ("application/xml", "text/xml") or fname_lower.endswith(".xml"):
                g = rdflib.Graph()
                g.parse(data=raw, format="xml")
                jsonld_text = g.serialize(format="json-ld")
                out_path = batch_dir / f"{name}.jsonld"
                out_path.write_text(jsonld_text)

            elif fct in ("application/json", "application/ld+json") or fname_lower.endswith((".json", ".jsonld")):
                text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
                out_path = batch_dir / f"{name}.jsonld"
                out_path.write_text(text)

            else:
                raise HTTPException(status_code=415, detail="Unsupported file type. Send .xml, .json, or .jsonld.")

        # ---- Case B: JSON body with rdfxml OR JSON-LD passthrough ----
        elif ct.startswith("application/json"):
            data = await request.json()
            name = (data.get("name") or "batch").rsplit(".", 1)[0]
            rdfxml = data.get("rdfxml")

            if isinstance(rdfxml, str) and rdfxml.strip():
                g = rdflib.Graph()
                g.parse(data=rdfxml, format="xml")
                jsonld_text = g.serialize(format="json-ld")
                out_path = batch_dir / f"{name}.jsonld"
                out_path.write_text(jsonld_text)
            else:
                import json as _json
                out_path = batch_dir / f"{name}.jsonld"
                out_path.write_text(_json.dumps(data))

        # ---- Case C: raw XML body ----
        elif ct.startswith("application/xml") or ct.startswith("text/xml"):
            xml_bytes = await request.body()
            if not xml_bytes:
                raise HTTPException(status_code=422, detail="Empty XML body.")
            g = rdflib.Graph()
            g.parse(data=xml_bytes, format="xml")
            jsonld_text = g.serialize(format="json-ld")
            out_path = batch_dir / "batch.jsonld"
            out_path.write_text(jsonld_text)

        else:
            raise HTTPException(
                status_code=415,
                detail="Send multipart/form-data with a file, application/json (with 'rdfxml' or JSON-LD), or application/xml.",
            )

        # Airflow reads from /opt/airflow/uploads/...
        file_location = f"/opt/airflow/uploads/{batch_dir.name}/{out_path.name}"
        workflow_id = await workflow.create_batch_from_uri(file_location)

    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {"uri": file_location, "workflow_id": workflow_id}
