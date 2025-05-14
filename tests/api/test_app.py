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
    # mock the call to airflow api
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/api/v1/dags/resource_loader/dagRuns$"),
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


@pytest.mark.asyncio
async def test_create_batch_from_upload(client, httpx_mock: HTTPXMock):
    # mock the call to airflow api
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/api/v1/dags/resource_loader/dagRuns$"),
        json={"dag_run_id": "12345"},
    )

    response = client.post(
        "/batches/upload/",
        headers={"X-User": "cataloger"},
        files={"file": open("README.md", "rb")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["uri"].endswith("README.md")
    assert data["workflow_id"] == "12345"

    upload_file = Path("./uploads/") / data["uri"]
    assert upload_file.is_file()
    assert upload_file.open("r").read() == open("README.md").read()
