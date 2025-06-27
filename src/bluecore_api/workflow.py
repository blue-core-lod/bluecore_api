import datetime
import os
import logging

import httpx

AIRFLOW_USER = os.environ.get("AIRFLOW_WWW_USER_USERNAME")
AIRFLOW_PASSWORD = os.environ.get("AIRFLOW_WWW_USER_PASSWORD")
AIRFLOW_INTERNAL_URL = os.environ.get("AIRFLOW_INTERNAL_URL").rstrip("/")


async def create_batch_from_uri(uri: str) -> str:
    """
    Start an Airflow DAG run to process data at a given URI. Returns the ID for the created DAG Run.
    A URI can have https, http, s3 or file protocol.
    """

    token = await get_token()

    url = f"{AIRFLOW_INTERNAL_URL}/api/v2/dags/resource_loader/dagRuns"
    now = datetime.datetime.now(tz=datetime.UTC).isoformat()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json={"logical_date": now, "conf": {"file": uri}},
            )
            resp.raise_for_status()
            job_id = resp.json().get("dag_run_id")
        except httpx.HTTPError as e:
            logging.error(e)
            if resp.status_code == 401:
                raise WorkflowError("Invalid credentials for Bluecore Workflow API")
            else:
                raise WorkflowError(f"Bluecore Workflow API at {url} is unavailable.")

        return job_id


async def get_token() -> str:
    """
    Get an Access Token from Keycloak for the user we need to speak to Airflow as.
    """

    # NOTE: once apache-airflow-providers-keycloak is available we will want to
    # switch over to using that instead of using http basic auth.
    #
    # See: https://github.com/apache/airflow/issues/51362

    resp = httpx.post(
        f"{AIRFLOW_INTERNAL_URL}/auth/token",
        json={"username": AIRFLOW_USER, "password": AIRFLOW_PASSWORD},
    )
    resp.raise_for_status()

    return resp.json()["access_token"]


class WorkflowError(Exception):
    pass
