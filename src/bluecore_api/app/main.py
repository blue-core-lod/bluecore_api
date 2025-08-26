import logging
import os
import sys
import time

from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from fastapi_keycloak_middleware import (
    AuthorizationMethod,
    CheckPermissions,
    KeycloakConfiguration,
    KeycloakMiddleware,
)

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../../")

from bluecore_api.middleware.keycloak_auth import (
    BypassKeycloakForGet,
    CompatibleFastAPI,
    enable_developer_mode,
)
from bluecore_api.middleware.redirect_headers import RedirectLocationMiddleware
from bluecore_api import workflow
from bluecore_api.change_documents.routes import change_documents
from bluecore_api.app.routes.cbd import endpoints as cbd_endpoints
from bluecore_api.app.routes.instances import endpoints as instance_routes
from bluecore_api.app.routes.other_resources import endpoints as resource_routes
from bluecore_api.app.routes.search import endpoints as search_routes
from bluecore_api.app.routes.works import endpoints as work_routes
from bluecore_api.schemas.schemas import BatchCreateSchema, BatchSchema

from starlette.middleware.base import BaseHTTPMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


"""Init base app"""
base_app = FastAPI()
base_app = FastAPI(root_path="/api")
base_app.include_router(change_documents)
base_app.include_router(cbd_endpoints)
base_app.include_router(instance_routes)
base_app.include_router(resource_routes)
base_app.include_router(search_routes)
base_app.include_router(work_routes)

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log incoming request
        logger.info(f"➡️ {request.method} {request.url.path} {request.headers}")
        
        response = await call_next(request)
        
        process_time = round((time.time() - start_time) * 1000, 2)
        
        # Log response status and duration
        logger.info(f"⬅️ {request.method} {request.url.path} - {response.status_code} {response.headers} ({process_time} ms)")
        
        return response


async def scope_mapper(claim_auth: list) -> list:
    """Role mapper"""
    permissions = claim_auth.get("roles", [])
    return permissions


"""Auth or dev mode config"""
if os.getenv("DEVELOPER_MODE") == "true":
    enable_developer_mode(base_app)
    application = base_app
else:
    keycloak_config = KeycloakConfiguration(
        use_introspection_endpoint=os.getenv("USE_KEYCLOAK_INTROSPECTION", "false")
        == "true",
        url=os.getenv("KEYCLOAK_INTERNAL_URL"),
        realm="bluecore",
        client_id=os.getenv("API_KEYCLOAK_CLIENT_ID"),
        authorization_method=AuthorizationMethod.CLAIM,
        authorization_claim="realm_access",
    )

    keycloak_middleware = KeycloakMiddleware(
        app=base_app,
        keycloak_configuration=keycloak_config,
        scope_mapper=scope_mapper,
        exclude_patterns=[],
    )

    middleware_wrapped_app = BypassKeycloakForGet(
        app=base_app, keycloak_middleware=keycloak_middleware
    )
    application = CompatibleFastAPI(app=middleware_wrapped_app)
    base_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allows for any local client to connect
        allow_methods=["*"],
        allow_headers=["*"],
    )
    base_app.add_middleware(RedirectLocationMiddleware)
    base_app.add_middleware(LoggingMiddleware)

@base_app.get("/")
async def index():
    """Public route for API root."""
    return {"message": "Blue Core API"}


@base_app.post(
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

    batch = {"uri": batch.uri, "workflow_id": workflow_id}
    return batch


@base_app.post(
    "/batches/upload/",
    response_model=BatchSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
)
async def create_batch_file(file: UploadFile = File(...)):
    """
    Authenticated route to upload a batch file and trigger
    the resource_loader Airflow DAG.
    """
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
