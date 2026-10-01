import os

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastapi_keycloak_middleware import FastApiUser, MatchStrategy, get_auth, get_user

KEYCLOAK_EXTERNAL_URL = os.getenv(
    "KEYCLOAK_EXTERNAL_URL", "http://localhost/keycloak"
).rstrip("/")

_openid_connect_url = f"{KEYCLOAK_EXTERNAL_URL}/realms/bluecore/protocol/openid-connect"

"""
Documents Keycloak in the OpenAPI spec and drives the /docs Authorize button.

auto_error must stay False. The scheme sits in the dependency tree of every
protected route, and with auto_error=True FastAPI would reject any request
without an Authorization header before the route runs -- which would break both
DEVELOPER_MODE and the test suite, neither of which sends one.
"""
keycloak_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=f"{_openid_connect_url}/auth",
    tokenUrl=f"{_openid_connect_url}/token",
    refreshUrl=f"{_openid_connect_url}/token",
    scheme_name="Keycloak",
    scopes={
        "openid": "Authenticate with Keycloak",
        "profile": "Read the caller's name and username",
        "email": "Read the caller's email address",
    },
    description=(
        "Keycloak bearer token from the `bluecore` realm. Authorization uses the "
        "`realm_access.roles` claim: `create`, `update`, and `export` grant write "
        "access, and `cataloger-read-only` denies it. Outside Swagger UI, get a "
        "token with `bluecore token` and send it as `Authorization: Bearer <token>`."
    ),
    auto_error=False,
)


class BluecoreCheckPermissions:
    def __init__(
        self,
        required_role: str | list[str],
        forbidden_role: str | list[str],
        required_strategy: MatchStrategy = MatchStrategy.AND,
        forbidden_strategy: MatchStrategy = MatchStrategy.OR,
    ):
        self.required_roles = self._normalize_roles(required_role)
        self.forbidden_roles = self._normalize_roles(forbidden_role)
        self.required_strategy = required_strategy
        self.forbidden_strategy = forbidden_strategy

    @staticmethod
    def _normalize_roles(roles: str | list[str]) -> list[str]:
        if isinstance(roles, str):
            return [roles]
        return roles

    @staticmethod
    def _check_roles(
        user_roles: list[str], roles_to_check: list[str], strategy: MatchStrategy
    ) -> bool:
        if strategy == MatchStrategy.AND:
            return all(role in user_roles for role in roles_to_check)
        elif strategy == MatchStrategy.OR:
            return any(role in user_roles for role in roles_to_check)
        else:
            raise ValueError(f"Unsupported match strategy: {strategy}")

    async def __call__(
        self,
        user: FastApiUser = Depends(get_user),
        auth: list[str] | None = Depends(get_auth),
        token: str | None = Security(keycloak_scheme),
    ) -> FastApiUser:
        # `token` is unused here (already validated by KeycloakMiddleware) but is
        # declared so that FastAPI finds SecurityBase in the dependency tree for
        # generating the OpenAPI security specification

        # Ensure the user is authenticated
        if not user or not user.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        # Roles are resolved by keycloak middleware + scope_mapper
        user_roles = auth or []

        # Verify the inclusion and exclusion conditions
        has_required = self._check_roles(
            user_roles, self.required_roles, self.required_strategy
        )
        has_forbidden = self._check_roles(
            user_roles, self.forbidden_roles, self.forbidden_strategy
        )

        if not has_required or has_forbidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=("Access denied."),
            )

        return user
