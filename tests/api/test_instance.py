import pathlib
import pytest

from fastapi.testclient import TestClient

from pytest_mock_resources import create_postgres_fixture

from bluecore.app.main import app, get_db
from bluecore_models.models import (
    Base,
    BibframeClass,
    Instance,
    ResourceBase,
    ResourceBibframeClass,
    Version,
    Work,
)

db_session = create_postgres_fixture(session=True)


@pytest.fixture
def client(db_session):
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

    def override_get_db():
        db = db_session
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(bind=db_session.get_bind())


def test_get_instance(client, db_session):
    db_session.add(
        Instance(
            id=2,
            uri="https://bluecore.info/instance/75d831b9-e0d6-40f0-abb3-e9130622eb8a",
            data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        )
    )
    response = client.get("/instances/2")
    assert response.status_code == 200
    assert response.json()["uri"].startswith(
        "https://bluecore.info/instance/75d831b9-e0d6-40f0-abb3-e9130622eb8a"
    )


def test_create_instance(client):
    payload = {
        "data": pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        "uri": "https://bluecore.info/instance/75d831b9-e0d6-40f0-abb3-e9130622eb8a",
        "work_id": None,
    }
    response = client.post("/instances/", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["data"] == payload["data"]
    assert data["uri"] == payload["uri"]


def test_update_instance(db_session, client):
    db_session.add(
        Instance(
            id=2,
            uri="https://bluecore.info/instance/75d831b9-e0d6-40f0-abb3-e9130622eb8a",
            data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        )
    )
    # Update URI
    new_uri = "https://bluecore.info/instance/0c1aed75-5108-4cb4-8601-4b73424bb0a7"
    put_response = client.put("/instances/2", json={"uri": new_uri})
    assert put_response.status_code == 200

    # Retrieve Instance
    get_response = client.get("/instances/2")
    data = get_response.json()
    assert data["uri"] == new_uri
