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
