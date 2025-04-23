import pathlib

import pytest
import rdflib

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


def test_get_work(client, db_session):
    db_session.add(
        Work(
            id=1,
            uri="https://bluecore.info/work/e0d6-40f0-abb3-e9130622eb8a",
            data=pathlib.Path("tests/blue-core-work.jsonld").read_text(),
        ),
    )
    response = client.get("/works/1")

    assert response.status_code == 200
    data = response.json()

    assert data["uri"].startswith(
        "https://bluecore.info/work/e0d6-40f0-abb3-e9130622eb8a"
    )


def test_create_work(client):
    payload = {
        "data": pathlib.Path("tests/blue-core-work.jsonld").read_text(),
        "uri": "https://bluecore.info/work/e0d6-40f0-abb3-e9130622eb8a",
    }
    create_response = client.post("/works/", json=payload)

    assert create_response.status_code == 201
    data = create_response.json()

    assert data["data"] == payload["data"]

    # Assert timestamps exist and are identical
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] == data["updated_at"], "created_at and updated_at should match on creation"


def test_update_work(client):
    payload = {
        "data": pathlib.Path("tests/blue-core-work.jsonld").read_text(),
        "uri": "https://bluecore.info/work/e0d6-40f0-abb3-e9130622eb8a",
    }
    create_response = client.post("/works/", json=payload)

    assert create_response.status_code == 201

    work_graph = rdflib.Graph()
    work_graph.parse(data=payload["data"], format="json-ld")

    work_graph.add(
        (
            rdflib.URIRef("https://bluecore.info/work/e0d6-40f0-abb3-e9130622eb8a"),
            rdflib.URIRef("https://schema.org/name"),
            rdflib.Literal("A New Work Name"),
        )
    )
    update_response = client.put(
        "/works/1", json={"data": work_graph.serialize(format="json-ld")}
    )

    assert update_response.status_code == 200

    get_response = client.get("/works/1")
    assert get_response.status_code == 200
    data = get_response.json()

    updated_work_graph = rdflib.Graph()
    updated_work_graph.parse(data=data["data"], format="json-ld")

    name = updated_work_graph.value(
        subject=rdflib.URIRef("https://bluecore.info/work/e0d6-40f0-abb3-e9130622eb8a"),
        predicate=rdflib.URIRef("https://schema.org/name"),
    )

    assert str(name) == "A New Work Name"

    # Assert timestamps exist and are now different
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] != data["updated_at"], "created_at and updated_at should not match on update"
