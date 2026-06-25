from fastapi import FastAPI, Request
from fastapi_keycloak_middleware import get_auth, get_user
from bluecore_models.models.version import CURRENT_USER_ID
from bluecore_api.middleware.helpers.keycloak_utils import (
    get_keycloak_user_info,
    log_user_info,
)


def enable_developer_mode(app):
    """Bypass Keycloak auth in dev mode by setting DEVELOPER_MODE=true"""
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


class CompatibleFastAPI(FastAPI):
    """Compatibility wrapper for FastAPI dev server support"""

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self._asgi_app = app

    async def __call__(self, scope, receive, send):
        await self._asgi_app(scope, receive, send)


def _with_api_root(paths: set[str]) -> set[str]:
    """
    The app is served both at the root and behind NGINX's "/api" root path, so
    every public GET path needs both forms. List each once below and let this
    expand it to {"/docs", "/api/docs"}
    """
    return {form for p in paths for form in (p, f"/api{p}")}


class BypassKeycloakForGet:
    """Add specific GET paths to bypass keycloak authentication"""

    EXACT_PATHS = _with_api_root(
        {
            "/",
            "/docs",
            "/openapi.json",
            "/favicon.ico",
        }
    )

    """Add GET path prefixes (e.g., /instances/, /works/)"""
    PREFIX_PATHS = _with_api_root(
        {
            "/instances/",
            "/works/",
            "/hubs/",
            "/resources/",
            "/change_documents/",
            "/search",
            "/cbd",
            "/static/",
            "/mcp",
        }
    )

    def __init__(self, app, keycloak_middleware):
        self.inner_app = app
        self.keycloak_middleware = keycloak_middleware

    async def __call__(self, scope, receive, send):
        method = scope["method"]
        path = scope["path"]

        if (
            method == "GET"
            and (
                path in self.EXACT_PATHS
                or any(path.startswith(prefix) for prefix in self.PREFIX_PATHS)
            )
        ) or method == "OPTIONS":
            await self.inner_app(scope, receive, send)
        else:
            await self.keycloak_middleware(scope, receive, send)


async def set_user_context(request: Request):
    """
    Store the current user's UID in CURRENT_USER_ID for Version.before_insert and
    log uid, username, email, first/last name for console log.
    """
    uid, username, email, given_name, family_name = get_keycloak_user_info(request)
    CURRENT_USER_ID.set(uid)
    log_user_info(uid, username, email, given_name, family_name, request)
