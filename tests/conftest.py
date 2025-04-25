import pytest

import pathlib
import os
import sys

from pytest_mock_resources import PostgresConfig, create_postgres_fixture

from fastapi import Request
from fastapi.testclient import TestClient
from fastapi_keycloak_middleware import get_auth, get_user

from bluecore_models.models import (
    Base,
    BibframeClass,
    Instance,
    ResourceBase,
    ResourceBibframeClass,
    Version,
    Work,
)

if os.getenv("DATABASE_URL") is None:
    os.environ["DATABASE_URL"] = (
        "postgresql://bluecore_admin:bluecore_admin@localhost/bluecore"
    )

os.environ["KEYCLOAK_URL"] = "http://localhost:8080/auth"
os.environ["KEYCLOAK_REALM"] = "bluecore"
os.environ["KEYCLOAK_CLIENT_ID"] = "bluecore"
os.environ["KEYCLOAK_CLIENT_SECRET"] = "abcded235"


@pytest.fixture(scope="session")
def pmr_postgres_config():
    return PostgresConfig(image="postgres:16-alpine")


db_session = create_postgres_fixture(session=True)


async def mocked_get_auth(request: Request):
    user = request.headers.get("X-User", "public")

    match user:
        case "cataloger":
            roles = ["create", "update"]

        case _:
            roles = []
    requested_roles = request.headers.get("X-Roles", "")
    if requested_roles:
        roles += requested_roles.split(",")

    return roles


async def mocked_get_user(request: Request):
    user = request.get("X-User", "public")
    return user


@pytest.fixture(scope="session")
def app(session_mocker):
    session_mocker.patch("fastapi_keycloak_middleware.setup_keycloak_middleware")

    from bluecore.app.main import app

    app.dependency_overrides[get_user] = mocked_get_user
    app.dependency_overrides[get_auth] = mocked_get_auth

    yield app


@pytest.fixture
def client(mocker, db_session, app):
    Base.metadata.create_all(
        bind=db_session.get_bind(),
        tables=[
            ResourceBase.__table__,
            BibframeClass.__table__,
            Instance.__table__,
            ResourceBibframeClass.__table__,
            Version.__table__,
            Work.__table__,
        ],
    )

    from bluecore.app.main import get_db

    def override_get_db():
        db = db_session
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    db_session.close()
    Base.metadata.drop_all(bind=db_session.get_bind())


root_directory = pathlib.Path(__file__).parent.parent
dir = root_directory / "src/"

sys.path.append(str(dir))
