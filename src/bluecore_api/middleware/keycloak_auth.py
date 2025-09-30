from fastapi import FastAPI, Request
from typing import Optional
import base64
import json
from fastapi_keycloak_middleware import get_auth, get_user
from bluecore_models.models.version import CURRENT_USER_ID


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
        "/resources/",
        "/api/resources/",
        "/api/instances/",
        "/api/works/",
        "/change_documents/",
        "/api/change_documents/",
        "/search",
        "/api/search",
        "/api/cbd",
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


def _decode_bearer_claims(auth_header: Optional[str]) -> dict:
    """
    Extract standard OIDC fields (sub, username, email, given/family name) from a
    Bearer JWT *without verification* (just to log who is calling). Returns a
    dict of claims or {} if the header is missing/invalid.
    """
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return {}
    token = auth_header.split(None, 1)[1]
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload_b64 = parts[1]
    pad = "=" * (-len(payload_b64) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + pad)
        payload = json.loads(raw.decode("utf-8"))
        keep = (
            "sub",
            "preferred_username",
            "username",
            "email",
            "given_name",
            "family_name",
            "name",
        )
        return {k: payload.get(k) for k in keep if k in payload}
    except Exception:
        return {}


# ==============================================================================
# Pull user-identifying fields *only* from the JWT claims we decoded above.
# Returns: (uid, username, email, given_name, family_name)
# ------------------------------------------------------------------------------
def _extract_identity_from_request(
    request: Request,
) -> tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Pull user-identifying fields from the JWT decoded above.
    Returns: (uid, username, email, given_name, family_name)
    """

    claims = _decode_bearer_claims(request.headers.get("authorization"))

    uid = (
        claims.get("sub")
        or claims.get("username")
        or claims.get("preferred_username")
        or claims.get("email")
        or "anonymous"
    )
    username = claims.get("preferred_username") or claims.get("username")
    email = claims.get("email")
    given_name = claims.get("given_name")
    family_name = claims.get("family_name")
    return uid, username, email, given_name, family_name


# ==============================================================================
# Store the current user's UID in CURRENT_USER_ID for Version.before_insert and
# print a concise line with uid, username, email, first/last name for debugging.
# Only reads the Bearer token (no middleware state).
# ------------------------------------------------------------------------------
async def set_user_context(request: Request):
    """
    Store the current user's UID in CURRENT_USER_ID for Version.before_insert and
    log uid, username, email, first/last name for console log.
    """
    uid, username, email, given_name, family_name = _extract_identity_from_request(
        request
    )
    CURRENT_USER_ID.set(uid)

    # Debug lines (no tokens printed)
    RESET = "\033[0m"
    BOLD = "\033[1m"
    MAGENTA = "\033[95m"
    print()
    print(f"{MAGENTA}{'#' * 71}{RESET}")
    print(f"{BOLD}{MAGENTA}User Info (from Bearer):{RESET}")
    print(f"{BOLD}{MAGENTA}UID:{RESET} {uid}")
    print(f"{BOLD}{MAGENTA}Username:{RESET} {username or '-'}")
    print(f"{BOLD}{MAGENTA}Email:{RESET} {email or '-'}")
    print(f"{BOLD}{MAGENTA}First Name:{RESET} {given_name or '-'}")
    print(f"{BOLD}{MAGENTA}Last Name:{RESET} {family_name or '-'}")
    print(f"{BOLD}{MAGENTA}API Path Called:{RESET} {request.url.path}")
    print(f"{MAGENTA}{'#' * 71}{RESET}")
    print()
