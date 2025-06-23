import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock


def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Blue Core API"}


@pytest.mark.asyncio
async def test_create_batch_from_uri(client, httpx_mock: HTTPXMock):
    # mock the call to get the keycloak token for the airflow_workflows client
    httpx_mock.add_response(
        method="POST",
        url=(re.compile(r"^http://airflow:8080/auth/token$")),
        json={"access_token": "xxx"},
    )

    # mock the call to airflow api
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/api/v2/dags/resource_loader/dagRuns$"),
        json={"dag_run_id": "12345"},
    )

    response = client.post(
        "/batches/",
        headers={"X-User": "cataloger"},
        json={"uri": "https://example.com"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["uri"] == "https://example.com"
    assert data["workflow_id"] == "12345"

    # ensure that the http call to airflow included the mocked access token
    assert httpx_mock.get_requests()[1].headers.get("Authorization") == "Bearer xxx"


@pytest.mark.asyncio
async def test_create_batch_from_upload(client, httpx_mock: HTTPXMock):
    # mock the call to get the keycloak token for the airflow_workflows client
    httpx_mock.add_response(
        method="POST",
        url=(re.compile(r"^http://airflow:8080/auth/token$")),
        json={"access_token": "xxx"},
    )

    # mock the call to airflow api
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/api/v2/dags/resource_loader/dagRuns$"),
        json={"dag_run_id": "12345"},
    )

    response = client.post(
        "/batches/upload/",
        files={"file": open("README.md", "rb")},
        headers={"X-User": "cataloger"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["uri"].endswith("README.md")
    assert data["workflow_id"] == "12345"

    # ensure that the http call to airflow included the mocked access token
    assert httpx_mock.get_requests()[1].headers.get("Authorization") == "Bearer xxx"

    # ensure that the file was saved to the uploads directory for airflow
    upload_file = Path("./uploads/") / data["uri"].split("uploads/")[-1]
    assert upload_file.is_file()
    assert upload_file.open("r").read() == open("README.md").read()
