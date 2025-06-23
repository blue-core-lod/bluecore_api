import os
import sys

from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, File, UploadFile, Request
from fastapi_keycloak_middleware import (
    AuthorizationMethod,
    CheckPermissions,
    KeycloakConfiguration,
    get_user,
    get_auth,
    setup_keycloak_middleware,
)

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../../")

from bluecore_api import workflow
from bluecore_api.change_documents.routes import change_documents
from bluecore_api.app.routes.instances import endpoints as instance_routes
from bluecore_api.app.routes.other_resources import endpoints as resource_routes
from bluecore_api.app.routes.works import endpoints as work_routes
from bluecore_api.schemas.schemas import (
    BatchCreateSchema,
    BatchSchema,
)

app = FastAPI()
app.include_router(change_documents)
app.include_router(instance_routes)
app.include_router(resource_routes)
app.include_router(work_routes)

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


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
