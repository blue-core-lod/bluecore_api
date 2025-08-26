import pytest

import pathlib
import os
import random
import sys

from pytest_mock_resources import PostgresConfig, create_postgres_fixture

from fastapi import Request
from fastapi.testclient import TestClient
from fastapi_keycloak_middleware import get_auth, get_user

from pymilvus import MilvusClient

from bluecore_models.models import (
    Base,
    BibframeClass,
    Instance,
    OtherResource,
    ResourceBase,
    ResourceBibframeClass,
    Version,
    Work,
)

from bluecore_models.utils.vector_db import init_collections

if os.getenv("DATABASE_URL") is None:
    os.environ["DATABASE_URL"] = (
        "postgresql://bluecore_admin:bluecore_admin@localhost/bluecore"
    )
os.environ["BLUECORE_URL"] = "https://bcld.info/"
os.environ["USE_KEYCLOAK_INTROSPECTION"] = "true"
os.environ["AIRFLOW_INTERNAL_URL"] = "http://airflow:8080"
os.environ["KEYCLOAK_INTERNAL_URL"] = "http://localhost:8080/auth"
os.environ["KEYCLOAK_REALM"] = "bluecore"
os.environ["API_KEYCLOAK_CLIENT_ID"] = "bluecore"
os.environ["API_KEYCLOAK_CLIENT_SECRET"] = "abcded235"

os.environ["ACTIVITY_STREAMS_PAGE_LENGTH"] = "2"
os.environ["ACTIVITY_STREAMS_HOST"] = "http://127.0.0.1:3000"


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

    from bluecore_api.app.main import base_app as test_app

    test_app.dependency_overrides[get_user] = mocked_get_user
    test_app.dependency_overrides[get_auth] = mocked_get_auth

    yield test_app


@pytest.fixture
def client(mocker, db_session, app):
    Base.metadata.create_all(
        bind=db_session.get_bind(),
        tables=[
            ResourceBase.__table__,
            BibframeClass.__table__,
            Instance.__table__,
            OtherResource.__table__,
            ResourceBibframeClass.__table__,
            Version.__table__,
            Work.__table__,
        ],
    )

    from bluecore_api.database import get_db

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


@pytest.fixture
def vector_client():
    client = MilvusClient("test-vector.db")
    init_collections(client)
    # Until milvus-lite PR https://github.com/milvus-io/milvus-lite/pull/303 is part of
    # release, need to add some data to avoid an exception when trying to query an empty
    # vector database
    doc = {"id": 1000, "vector": [random.uniform(-1, 1) for _ in range(768)]}
    client.insert(
        "instances",
        [
            doc,
        ],
    )
    client.insert(
        "works",
        [
            doc,
        ],
    )

    yield client

    client.delete(collection_name="instances", filter="version == 1")


@pytest.fixture(autouse=True)
def remove_vector_db():
    vector_db_path = root_directory / "test-vector.db"
    if vector_db_path.exists():
        vector_db_path.unlink()
