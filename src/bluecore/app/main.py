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
from bluecore import workflow
from bluecore.database import get_db
from bluecore.change_documents.routes import change_documents
from bluecore.schemas.schemas import (
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


# ==============================================================================
# Bypass Keycloak auth in local-only dev mode by setting DEVELOPER_MODE=true
# Sets up mocked auth and user dependencies instead of requiring real tokens
# ------------------------------------------------------------------------------
def enable_developer_mode(app):
    developer_permissions = ["create", "update"]  # update to add more permissions

    async def mocked_get_auth(request: Request):
        return developer_permissions

    async def mocked_get_user(request: Request):
        return "developer"

    app.dependency_overrides[get_auth] = mocked_get_auth
    app.dependency_overrides[get_user] = mocked_get_user
    print(
        "\033[1;35m🚧 DEVELOPER_MODE is ON — Keycloak is bypassed with mock permissions\033[0m"
    )


async def scope_mapper(claim_auth: list) -> list:
    permissions = claim_auth.get("roles", [])
    return permissions


if os.getenv("DEVELOPER_MODE") == "true":
    enable_developer_mode(app)
else:
    keycloak_config = KeycloakConfiguration(
        url=os.getenv("KEYCLOAK_URL"),
        realm=os.getenv("KEYCLOAK_REALM"),
        client_id=os.getenv("KEYCLOAK_CLIENT_ID"),
        client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET"),
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
    db_instance = Instance(
        data=instance.data,
        uri=instance.uri,
        work_id=instance.work_id,
        created_at=time_now,
        updated_at=time_now,
    )
    db.add(db_instance)
    db.commit()
    db.refresh(db_instance)
    return db_instance


@app.get("/instances/{instance_id}", response_model=InstanceSchema)
async def read_instance(instance_id: int, db: Session = Depends(get_db)):
    db_instance = db.query(Instance).filter(Instance.id == instance_id).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    return db_instance


@app.put(
    "/instances/{instance_id}",
    response_model=InstanceSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
)
async def update_instance(
    instance_id: int, instance: InstanceUpdateSchema, db: Session = Depends(get_db)
):
    db_instance = db.query(Instance).filter(Instance.id == instance_id).first()
    if db_instance is None:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")

    # Update fields if they are provided
    if instance.data is not None:
        db_instance.data = instance.data
    if instance.uri is not None:
        db_instance.uri = instance.uri
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
    db_work = Work(
        data=work.data,
        uri=work.uri,
        created_at=time_now,
        updated_at=time_now,
    )
    db.add(db_work)
    db.commit()
    db.refresh(db_work)
    return db_work


@app.get("/works/{work_id}", response_model=WorkSchema)
async def read_work(work_id: int, db: Session = Depends(get_db)):
    db_work = db.query(Work).filter(Work.id == work_id).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_id} not found")
    return db_work


@app.put(
    "/works/{work_id}",
    response_model=WorkSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
)
async def update_work(
    work_id: int, work: WorkUpdateSchema, db: Session = Depends(get_db)
):
    db_work = db.query(Work).filter(Work.id == work_id).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_id} not found")

    # Update fields if they are provided
    if work.data is not None:
        db_work.data = work.data
    if work.uri is not None:
        db_work.uri = work.uri

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
        batch_file = upload_dir / str(uuid4()) / file.filename
        batch_file.parent.mkdir(parents=False, exist_ok=True)

        with batch_file.open("wb") as fh:
            while buff := file.file.read(1024 * 1024):
                fh.write(buff)

        uri = "file:{batch_file.absolute()}"
        workflow_id = await workflow.create_batch_from_uri(uri)

    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))

    batch = {"uri": str(batch_file.relative_to(upload_dir)), "workflow_id": workflow_id}
    return batch
