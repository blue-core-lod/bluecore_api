import pathlib
import pytest

from bluecore_models.models import Instance


def test_get_instance(client, db_session):
    db_session.add(
        Instance(
            id=2,
            uuid="75d831b9-e0d6-40f0-abb3-e9130622eb8a",
            uri="https://bluecore.info/instance/75d831b9-e0d6-40f0-abb3-e9130622eb8a",
            data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        )
    )

    response = client.get("/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a")
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
    response = client.post("/instances/", headers={"X-User": "cataloger"}, json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["data"] == payload["data"]
    assert data["uri"] == payload["uri"]

    # Assert timestamps exist and are identical
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] == data["updated_at"], (
        "created_at and updated_at should match on creation"
    )


def test_update_instance(client, db_session):
    db_session.add(
        Instance(
            id=2,
            uuid="75d831b9-e0d6-40f0-abb3-e9130622eb8a",
            uri="https://bcld.info/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a",
            data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        )
    )

    # Update URI
    new_uri = "https://bcld.info/instances/e1b504b5-ed92-429a-9abf-8e49a3b6ff40"
    put_response = client.put(
        "/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a",
        headers={"X-User": "cataloger"},
        json={"uri": new_uri},
    )
    assert put_response.status_code == 200

    # Retrieve Instance
    get_response = client.get("/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a")
    data = get_response.json()
    assert data["uri"] == new_uri

    # Assert timestamps exist and are now different
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] != data["updated_at"], (
        "created_at and updated_at should not match on update"
    )
