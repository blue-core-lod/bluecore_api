import json
import re

import pytest
from pytest_httpx import HTTPXMock


@pytest.mark.asyncio
async def test_export(client, httpx_mock: HTTPXMock):
    # Mock calls the keycloak token for the airflow_workflows client
    httpx_mock.add_response(
        method="POST",
        url=(re.compile(r"^http://airflow:8080/auth/token$")),
        json={"access_token": "xxx"},
    )

    # mock the call to airflow api
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/api/v2/dags/monitor_institutions_exports/dagRuns$"),
        json={"dag_run_id": "12345"},
    )

    response = client.post(
        "/export/",
        headers={"X-User": "cataloger"},
        json={
            "instance_uri": "https://bcld.info/instances/8836b3c5-9bc6-421b-9591-df25499cd93c"
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_id"].startswith("12345")
    assert data["instance_uri"].endswith("df25499cd93c")

    # ensure the conf sent to airflow always includes both keys, with the unused
    # identifier sent as null
    dag_run_request = httpx_mock.get_requests()[1]
    conf = json.loads(dag_run_request.content)["conf"]
    assert conf["resource"].endswith("df25499cd93c")
    assert conf["local_id"] is None


@pytest.mark.asyncio
async def test_export_with_local_id(client, httpx_mock: HTTPXMock):
    # Mock calls the keycloak token for the airflow_workflows client
    httpx_mock.add_response(
        method="POST",
        url=(re.compile(r"^http://airflow:8080/auth/token$")),
        json={"access_token": "xxx"},
    )

    # mock the call to airflow api
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/api/v2/dags/monitor_institutions_exports/dagRuns$"),
        json={"dag_run_id": "12345"},
    )

    response = client.post(
        "/export/",
        headers={"X-User": "cataloger"},
        json={
            "instance_uri": "https://bcld.info/instances/8836b3c5-9bc6-421b-9591-df25499cd93c",
            "local_id": "a123456",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_id"].startswith("12345")
    assert data["local_id"] == "a123456"
    assert data["instance_uri"].endswith("df25499cd93c")

    # ensure the conf sent to airflow always includes both keys
    dag_run_request = httpx_mock.get_requests()[1]
    conf = json.loads(dag_run_request.content)["conf"]
    assert conf["local_id"] == "a123456"
    assert conf["resource"].endswith("df25499cd93c")


@pytest.mark.asyncio
async def test_export_rejects_local_id_without_instance_uri(
    client, httpx_mock: HTTPXMock
):
    response = client.post(
        "/export/",
        headers={"X-User": "cataloger"},
        json={"local_id": "a123456"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_rejects_missing_instance_uri(client, httpx_mock: HTTPXMock):
    response = client.post(
        "/export/",
        headers={"X-User": "cataloger"},
        json={},
    )

    assert response.status_code == 422
