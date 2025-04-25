from fastapi import Depends, FastAPI, HTTPException, File, UploadFile, Request
from fastapi_keycloak_middleware import (
    AuthorizationMethod,
    CheckPermissions,
    KeycloakConfiguration,
    get_user,
    get_auth,
    setup_keycloak_middleware,
)
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from uuid import uuid4

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../../")
from bluecore import workflow
from bluecore.app.change_notifications.activity_streams import ActivityStreamsGenerator
from bluecore.app.resource_manager.resource_manager import ResourceManager
from bluecore.schemas import (
    ActivityStreamsChangeSetSchema,
    ActivityStreamsEntryPointSchema,
    BatchCreateSchema,
    BatchSchema,
    InstanceSchema,
    InstanceCreateSchema,
    InstanceUpdateSchema,
    WorkSchema,
    WorkCreateSchema,
    WorkUpdateSchema,
)
from bluecore.utils.constants import ACTIVITY_STREAMS_PAGE_LENGTH
from bluecore_models.models import Instance, Work

keycloak_config = KeycloakConfiguration(
    url=os.getenv("KEYCLOAK_URL"),
    realm=os.getenv("KEYCLOAK_REALM"),
    client_id=os.getenv("KEYCLOAK_CLIENT_ID"),
    client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET"),
    authorization_method=AuthorizationMethod.CLAIM,
    authorization_claim="realm_access",
)

app = FastAPI()


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
    # Add Keycloak middleware
    setup_keycloak_middleware(
        app,
        keycloak_configuration=keycloak_config,
        exclude_patterns=["/docs", "/openapi.json"],
        scope_mapper=scope_mapper,
    )

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
engine = create_engine(DATABASE_URL)
session_maker = sessionmaker(autocommit=False, autoflush=False, bind=engine)
page_length: int = int(os.getenv("PAGE_LENGTH", ACTIVITY_STREAMS_PAGE_LENGTH))
ACTIVITY_STREAMS_GENERATOR = ActivityStreamsGenerator(page_length=page_length)
RESOURCE_MANAGER = ResourceManager()


def get_db():
    db = session_maker()
    try:
        yield db
    finally:
        db.close()


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
    return RESOURCE_MANAGER.create_instance(instance=instance, db=db)


@app.get("/instances/{instance_id}", response_model=InstanceSchema)
async def read_instance(instance_id: int, db: Session = Depends(get_db)):
    return RESOURCE_MANAGER.read_instance(instance_id=instance_id, db=db)


@app.put(
    "/instances/{instance_id}",
    response_model=InstanceSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
)
async def update_instance(
    instance_id: int, instance: InstanceUpdateSchema, db: Session = Depends(get_db)
):
    return RESOURCE_MANAGER.update_instance(
        instance_id=instance_id, instance=instance, db=db
    )


@app.post(
    "/works/",
    response_model=WorkSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
)
async def create_work(work: WorkCreateSchema, db: Session = Depends(get_db)):
    return RESOURCE_MANAGER.create_work(work=work, db=db)


@app.get("/works/{work_id}", response_model=WorkSchema)
async def read_work(work_id: int, db: Session = Depends(get_db)) -> Work:
    return RESOURCE_MANAGER.read_work(work_id=work_id, db=db)


@app.put(
    "/works/{work_id}",
    response_model=WorkSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
)
async def update_work(
    work_id: int, work: WorkUpdateSchema, db: Session = Depends(get_db)
) -> Work:
    return RESOURCE_MANAGER.update_work(work_id=work_id, work=work, db=db)


@app.get(
    "/change_documents/works/activitystreams/feed",
    response_model=ActivityStreamsEntryPointSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def works_activity_streams_feed(
    id: int = 0, db: Session = Depends(get_db)
) -> ActivityStreamsEntryPointSchema:
    return ACTIVITY_STREAMS_GENERATOR.works_activity_streams_feed(db=db)


@app.get(
    "/change_documents/works/activitystreams/page/{id}",
    response_model=ActivityStreamsChangeSetSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def works_activity_streams_page(
    id: int = 0, db: Session = Depends(get_db)
) -> ActivityStreamsChangeSetSchema:
    return ACTIVITY_STREAMS_GENERATOR.works_activity_streams_page(id=id, db=db)


@app.get(
    "/change_documents/instances/activitystreams/feed",
    response_model=ActivityStreamsEntryPointSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def instances_activity_streams_feed(
    id: int = 0, db: Session = Depends(get_db)
) -> ActivityStreamsEntryPointSchema:
    return ACTIVITY_STREAMS_GENERATOR.instances_activity_streams_feed(db=db)


@app.get(
    "/change_documents/instances/activitystreams/page/{id}",
    response_model=ActivityStreamsChangeSetSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def instances_activity_streams_page(
    id: int = 0, db: Session = Depends(get_db)
) -> ActivityStreamsChangeSetSchema:
    return ACTIVITY_STREAMS_GENERATOR.instances_activity_streams_page(id=id, db=db)


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
