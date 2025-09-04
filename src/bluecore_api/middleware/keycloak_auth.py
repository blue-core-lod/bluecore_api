from fastapi import FastAPI, Request
from fastapi_keycloak_middleware import get_auth, get_user


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


class BypassKeycloakForGet:
    """Add specific GET paths to bypass keycloak authentication"""

    EXACT_PATHS = {
        "/",
        "/api/",
        "/docs",
        "/api/docs",
        "/openapi.json",
        "/api/openapi.json",
    }

    """Add GET path prefixes (e.g., /instances/, /works/)"""
    PREFIX_PATHS = {
        "/instances/",
        "/works/",
        "/api/instances/",
        "/api/works/",
        "/change_documents/",
        "/api/change_documents/",
        "/search",
        "/api/search",
        "/api/cbd"
    }

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
