import os
import sys
from fastapi import FastAPI, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP, AuthConfig
from bluecore_api.app.config.logging_setup import setup_logging
from fastapi_keycloak_middleware import (
    AuthorizationMethod,
    CheckPermissions,
    KeycloakConfiguration,
    KeycloakMiddleware,
)
from fastapi_keycloak_middleware.schemas.match_strategy import MatchStrategy

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../../")

from bluecore_api.middleware.keycloak_auth import (
    BypassKeycloakForGet,
    CompatibleFastAPI,
    enable_developer_mode,
    set_user_context,
)

from bluecore_api.middleware.redirect_headers import RedirectLocationMiddleware
from bluecore_api.change_documents.routes import change_documents
from bluecore_api.app.routes.cbd import endpoints as cbd_endpoints
from bluecore_api.app.routes.instances import endpoints as instance_routes
from bluecore_api.app.routes.other_resources import endpoints as resource_routes
from bluecore_api.app.routes.search import endpoints as search_routes
from bluecore_api.app.routes.works import endpoints as work_routes
from bluecore_api.app.routes.batches import endpoints as batch_endpoints

"""Initialize logging config"""
setup_logging()

"""Init base app"""
base_app = FastAPI(root_path="/api", dependencies=[Depends(set_user_context)])
base_app.include_router(change_documents)
base_app.include_router(cbd_endpoints)
base_app.include_router(instance_routes)
base_app.include_router(resource_routes)
base_app.include_router(search_routes)
base_app.include_router(work_routes)
base_app.include_router(batch_endpoints)

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


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
    base_app.add_middleware(RedirectLocationMiddleware)

base_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows for any local client to connect
    allow_methods=["*"],
    allow_headers=["*"],
)

mcp = FastApiMCP(
    base_app,
    auth_config=AuthConfig(
        dependencies=[
            Depends(
                CheckPermissions(["create", "update"], match_strategy=MatchStrategy.OR)
            )
        ]
    ),
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


mcp.mount_http()
