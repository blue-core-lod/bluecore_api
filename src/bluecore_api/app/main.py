import os
import sys

from pathlib import Path
from uuid import uuid4
from datetime import datetime, UTC
from fastapi import Depends, FastAPI, HTTPException, File, UploadFile, Request
from fastapi_keycloak_middleware import (
    AuthorizationMethod,
    CheckPermissions,
    KeycloakConfiguration,
    get_user,
    get_auth,
    setup_keycloak_middleware,
)
from sqlalchemy.orm import Session

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../../")
from bluecore_models.models import Instance, Work
from bluecore_models.utils.graph import handle_external_subject
from bluecore_api import workflow
from bluecore_api.database import get_db
from bluecore_api.change_documents.routes import change_documents
from bluecore_api.schemas.schemas import (
    BatchCreateSchema,
    BatchSchema,
    InstanceCreateSchema,
    InstanceSchema,
    InstanceUpdateSchema,
    WorkCreateSchema,
    WorkSchema,
    WorkUpdateSchema,
)

app = FastAPI()
app.include_router(change_documents)

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


# ==============================================================================
# Bypass Keycloak auth in local-only dev mode by setting BYPASS_KEYCLOAK=true
# Sets up mocked auth and user dependencies instead of requiring real tokens
# ------------------------------------------------------------------------------
def bypass_keycloak(app):
    developer_permissions = ["create", "update"]  # update to add more permissions

    async def mocked_get_auth(request: Request):
        return developer_permissions

    async def mocked_get_user(request: Request):
        return "developer"

    app.dependency_overrides[get_auth] = mocked_get_auth
    app.dependency_overrides[get_user] = mocked_get_user
    print(
        "\033[1;35m🚧 BYPASS_KEYCLOAK is ON — Keycloak is bypassed with mock permissions\033[0m"
    )


async def scope_mapper(claim_auth: list) -> list:
    permissions = claim_auth.get("roles", [])
    return permissions


if os.getenv("BYPASS_KEYCLOAK") == "true":
    bypass_keycloak(app)
else:
    keycloak_config = KeycloakConfiguration(
        url=os.getenv("KEYCLOAK_URL"),
        realm="bluecore",
        client_id=os.getenv("API_KEYCLOAK_CLIENT_ID"),
        authorization_method=AuthorizationMethod.CLAIM,
        authorization_claim="realm_access",
    )

    # Add Keycloak middleware
    setup_keycloak_middleware(
        app,
        keycloak_configuration=keycloak_config,
        exclude_patterns=["/docs", "/openapi.json", "/api/docs", "/api/openapi.json"],
        scope_mapper=scope_mapper,
    )


@app.get("/")
async def index():
    return {"message": "Blue Core API"}


@app.post(
    "/instances/",
    response_model=InstanceSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
)
async def create_instance(
    instance: InstanceCreateSchema, db: Session = Depends(get_db)
):
    time_now = datetime.now(UTC)
    updated_payload = handle_external_subject(
        data=instance.data, type="instances", bluecore_base_url=BLUECORE_URL
    )
    db_instance = Instance(
        data=updated_payload.get("data"),
        uri=updated_payload.get("uri"),
        work_id=instance.work_id,
        uuid=updated_payload.get("uuid"),
        created_at=time_now,
        updated_at=time_now,
    )
    db.add(db_instance)
    db.commit()
    db.refresh(db_instance)
    return db_instance


@app.get("/instances/{instance_uuid}", response_model=InstanceSchema)
async def read_instance(instance_uuid: str, db: Session = Depends(get_db)):
    db_instance = db.query(Instance).filter(Instance.uuid == instance_uuid).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    return db_instance


@app.put(
    "/instances/{instance_uuid}",
    response_model=InstanceSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
)
async def update_instance(
    instance_uuid: str, instance: InstanceUpdateSchema, db: Session = Depends(get_db)
):
    db_instance = db.query(Instance).filter(Instance.uuid == instance_uuid).first()
    if db_instance is None:
        raise HTTPException(
            status_code=404, detail=f"Instance {instance_uuid} not found"
        )

    # Update fields if they are provided
    if instance.data is not None:
        db_instance.data = instance.data
    if instance.work_id is not None:
        db_instance.work_id = instance.work_id

    db.commit()
    db.refresh(db_instance)
    return db_instance


@app.post(
    "/works/",
    response_model=WorkSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
)
async def create_work(work: WorkCreateSchema, db: Session = Depends(get_db)):
    time_now = datetime.now(UTC)
    updated_payload = handle_external_subject(
        data=work.data, type="works", bluecore_base_url=BLUECORE_URL
    )
    db_work = Work(
        data=updated_payload.get("data"),
        uri=updated_payload.get("uri"),
        uuid=updated_payload.get("uuid"),
        created_at=time_now,
        updated_at=time_now,
    )
    db.add(db_work)
    db.commit()
    db.refresh(db_work)
    return db_work


@app.get("/works/{work_uuid}", response_model=WorkSchema)
async def read_work(work_uuid: str, db: Session = Depends(get_db)):
    db_work = db.query(Work).filter(Work.uuid == work_uuid).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")
    return db_work


@app.put(
    "/works/{work_uuid}",
    response_model=WorkSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
)
async def update_work(
    work_uuid: str, work: WorkUpdateSchema, db: Session = Depends(get_db)
):
    db_work = db.query(Work).filter(Work.uuid == work_uuid).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")

    # Update data if it is provided
    if work.data is not None:
        db_work.data = work.data

    db.commit()
    db.refresh(db_work)
    return db_work


@app.post(
    "/batches/",
    response_model=BatchSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
)
async def create_batch(batch: BatchCreateSchema):
    try:
        workflow_id = await workflow.create_batch_from_uri(batch.uri)
    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))

    batch = {"uri": batch.uri, "workflow_id": workflow_id}
    return batch


@app.post(
    "/batches/upload/",
    response_model=BatchSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
)
async def create_batch_file(file: UploadFile = File(...)):
    try:
        upload_dir = Path("./uploads")
        batch_file = f"{uuid4()}/{file.filename}"
        batch_path = upload_dir / batch_file
        batch_path.parent.mkdir(parents=True, exist_ok=True)

        with batch_path.open("wb") as fh:
            while buff := file.file.read(1024 * 1024):
                fh.write(buff)

        # Pattern expected by the Airflow resource_loader DAG
        file_location = f"/opt/airflow/uploads/{batch_file}"
        workflow_id = await workflow.create_batch_from_uri(file_location)

    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))

    batch = {"uri": file_location, "workflow_id": workflow_id}
    return batch
