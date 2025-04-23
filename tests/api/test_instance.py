import pathlib
import pytest

from bluecore_models.models import Instance


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


def test_create_instance(client, mocker):
    # mocker.patch("bluecore.app.main.CheckPermissions")

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


def test_update_instance(client, db_session):
    db_session.add(
        Instance(
            id=2,
            uri="https://bluecore.info/instance/75d831b9-e0d6-40f0-abb3-e9130622eb8a",
            data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        )
    )

    # Update URI
    new_uri = "https://bluecore.info/instance/0c1aed75-5108-4cb4-8601-4b73424bb0a7"
    put_response = client.put(
        "/instances/2", headers={"X-User": "cataloger"}, json={"uri": new_uri}
    )
    assert put_response.status_code == 200

    # Retrieve Instance
    get_response = client.get("/instances/2")
    data = get_response.json()
    assert data["uri"] == new_uri
