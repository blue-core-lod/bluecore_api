import os
import sys

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi_keycloak_middleware import (
    AuthorizationMethod,
    CheckPermissions,
    KeycloakConfiguration,
    KeycloakMiddleware,
    MatchStrategy,
    get_auth,
)
from fastapi_mcp import AuthConfig, FastApiMCP

from bluecore_api.app.config.logging_setup import setup_logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../../")

from bluecore_models.utils.graph import CONTEXT

from bluecore_api.app.routes.batches import endpoints as batch_endpoints
from bluecore_api.app.routes.convert import endpoints as convert_endpoints
from bluecore_api.app.routes.export import endpoints as export_routes
from bluecore_api.app.routes.health import endpoints as health_routes
from bluecore_api.app.routes.hubs import endpoints as hub_routes
from bluecore_api.app.routes.instances import endpoints as instance_routes
from bluecore_api.app.routes.other_resources import endpoints as resource_routes
from bluecore_api.app.routes.profiles import endpoints as profile_routes
from bluecore_api.app.routes.search import endpoints as search_routes
from bluecore_api.app.routes.versions import endpoints as version_routes
from bluecore_api.app.routes.works import endpoints as work_routes
from bluecore_api.change_documents.routes import change_documents
from bluecore_api.middleware.keycloak_auth import (
    BypassKeycloakForGet,
    CompatibleFastAPI,
    enable_developer_mode,
    set_user_context,
)
from bluecore_api.middleware.redirect_headers import RedirectLocationMiddleware

"""Initialize logging config"""
setup_logging()

"""
OpenAPI tag metadata. The order here is the order sections appear in the /docs and /redoc pages.
"""
openapi_tags = [
    {"name": "Hubs", "description": "BIBFRAME Hubs gathering related Works."},
    {"name": "Works", "description": "BIBFRAME Works."},
    {"name": "Instances", "description": "BIBFRAME Instances belonging to a Work."},
    {
        "name": "Resources",
        "description": "JSON-LD resources used to support Work and Instances.",
    },
    {
        "name": "Profiles",
        "description": "Resource profiles (e.g. Sinopia profiles) used to drive editing.",
    },
    {
        "name": "Versions",
        "description": "Version history for Hubs, Works, and Instances.",
    },
    {
        "name": "Search",
        "description": "Full-text and vector search for Works, Instances, Hubs, Resources.",
    },
    {
        "name": "Change Documents",
        "description": "Activity Streams change feeds for downstream consumers.",
    },
    {"name": "Batches", "description": "Bulk ingestion via Airflow."},
    {"name": "Export", "description": "Resource export."},
    {"name": "Convert", "description": "Format conversion utilities."},
    {"name": "Health", "description": "Service health check."},
]

"""Init base app"""
base_app = FastAPI(
    root_path="/api",
    dependencies=[Depends(set_user_context)],
    openapi_tags=openapi_tags,
    swagger_ui_parameters={
        "displayRequestDuration": True,  # Show response time on each call
        "filter": True,  # Add a search box to filter operations by name
        "defaultModelsExpandDepth": 0,  # Start the "Schemas" section collapsed
    },
    swagger_ui_init_oauth={
        "clientId": os.getenv("API_KEYCLOAK_CLIENT_ID", ""),
        "usePkceWithAuthorizationCodeGrant": True,
        "scopes": "openid profile email",
    },
)
base_app.include_router(hub_routes, tags=["Hubs"])
base_app.include_router(work_routes, tags=["Works"])
base_app.include_router(instance_routes, tags=["Instances"])
base_app.include_router(resource_routes, tags=["Resources"])
base_app.include_router(profile_routes, tags=["Profiles"])
base_app.include_router(version_routes, tags=["Versions"])
base_app.include_router(search_routes, tags=["Search"])
base_app.include_router(change_documents, tags=["Change Documents"])
base_app.include_router(batch_endpoints, tags=["Batches"])
base_app.include_router(export_routes, tags=["Export"])
base_app.include_router(convert_endpoints, tags=["Convert"])

# MCP write methods require a create/update permission
_mcp_write_permission = CheckPermissions(
    ["create", "update"], match_strategy=MatchStrategy.OR
)


async def mcp_permissions(request: Request, auth=Depends(get_auth)):
    """
    Auth for the MCP mount.
    GET /mcp (the SSE/discovery stream) is public it's and bypassed upstream by
    BypassKeycloakForGet, so get_auth is None here
    """
    if request.method == "GET":
        return
    _mcp_write_permission(user=None, auth=auth or [])


mcp = FastApiMCP(
    base_app,
    auth_config=AuthConfig(dependencies=[Depends(mcp_permissions)]),
)
mcp.mount_http()

# Registered after the MCP mount so the health check stays out of the tool list;
# it's for load balancers and deploy checks, not for MCP clients.
base_app.include_router(health_routes, tags=["Health"])

# Serve CSS/images for HTML views. Templates reference these at `{{ BLUECORE_URL }}static/...` (see app/views/templating.py).
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@base_app.get("/static/{path:path}", include_in_schema=False)
async def static_files(path: str) -> FileResponse:
    full_path = os.path.normpath(os.path.join(STATIC_DIR, path))
    if os.path.commonpath([full_path, STATIC_DIR]) != STATIC_DIR or not os.path.isfile(
        full_path
    ):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(full_path)


BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


async def scope_mapper(claim_auth: list) -> list:
    """Role mapper — keycloak middleware passes the decoded claim as a dict at runtime."""
    permissions = claim_auth.get("roles", [])  # ty: ignore[unresolved-attribute]
    return permissions


"""Auth or dev mode config"""
if os.getenv("DEVELOPER_MODE") == "true":
    enable_developer_mode(base_app)
    application = base_app
else:
    keycloak_config = KeycloakConfiguration(
        use_introspection_endpoint=os.getenv("USE_KEYCLOAK_INTROSPECTION", "false")
        == "true",
        url=os.getenv("KEYCLOAK_INTERNAL_URL", ""),
        realm="bluecore",
        client_id=os.getenv("API_KEYCLOAK_CLIENT_ID", ""),
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
    base_app.add_middleware(RedirectLocationMiddleware)

base_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows for any local client to connect
    allow_methods=["*"],
    allow_headers=["*"],
)


@base_app.get("/")
async def index():
    """Public route for API root."""
    return {"message": "Blue Core API"}


@base_app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """
    Prevents '404 Not Found' when using API in browser;
    204 = no content; cache it so the browser won't ask again soon
    """
    return Response(status_code=204, headers={"Cache-Control": "public, max-age=86400"})


@base_app.get("/context.jsonld")
async def context_jsonld():
    # Sinopia rejects both a bare mapping anda non-JSON-LD media type.
    return JSONResponse({"@context": CONTEXT}, media_type="application/ld+json")


"""
Error responses for any operation that carries a security requirement.

FastAPI derives the requirement itself from the SecurityBase in the route's
dependency tree (see middleware/bluecore_check_permissions.py), but it can't 
know which failures that implies. Attaching them by inspecting the finished 
schema keeps new routes covered without repeating `responses=` on every 
    decorator.
"""
_UNAUTHORIZED_RESPONSE = {
    "description": "Missing or invalid Keycloak bearer token.",
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {"detail": {"type": "string"}},
            },
            "example": {"detail": "Not authenticated"},
        }
    },
}

_FORBIDDEN_RESPONSE = {
    "description": "Token lacks the required realm role, or holds a forbidden one.",
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {"detail": {"type": "string"}},
            },
            "example": {"detail": "Access denied."},
        }
    },
}

_default_openapi = base_app.openapi


def openapi_with_auth_responses():
    if base_app.openapi_schema:
        return base_app.openapi_schema
    # _default_openapi() builds and caches base_app.openapi_schema; we mutate
    # that same dict in place, so the injection is cached along with it.
    schema = _default_openapi()
    for operations in schema["paths"].values():
        for operation in operations.values():
            if not isinstance(operation, dict) or not operation.get("security"):
                continue
            responses = operation.setdefault("responses", {})
            responses.setdefault("401", _UNAUTHORIZED_RESPONSE)
            responses.setdefault("403", _FORBIDDEN_RESPONSE)
    return schema


base_app.openapi = openapi_with_auth_responses  # ty: ignore
