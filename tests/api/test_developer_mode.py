"""Tests for enable_developer_mode, the DEVELOPER_MODE Keycloak bypass.

These build a fresh FastAPI() rather than using the session `app` fixture:
conftest installs its own get_user/get_auth overrides on that app, which would
mask whatever enable_developer_mode installs.
"""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from bluecore_api.constants import READ_ONLY_ROLES, KeycloakRole
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)
from bluecore_api.middleware.keycloak_auth import enable_developer_mode


def _developer_client(role: KeycloakRole) -> TestClient:
    app = FastAPI()

    @app.post("/protected")
    async def protected(user=Depends(BCP(role, READ_ONLY_ROLES))):
        return {"identity": user.identity}

    enable_developer_mode(app)
    return TestClient(app)


def test_developer_mode_passes_permission_check():
    # Regression for #351: get_user returned the bare string "developer", so
    # BluecoreCheckPermissions raised AttributeError on .is_authenticated and
    # every protected route came back 500.
    response = _developer_client(KeycloakRole.CREATE).post("/protected")

    assert response.status_code == 200
    assert response.json() == {"identity": "developer"}


def test_developer_mode_grants_every_role_it_mocks():
    for role in (KeycloakRole.CREATE, KeycloakRole.UPDATE, KeycloakRole.EXPORT):
        assert _developer_client(role).post("/protected").status_code == 200, role
