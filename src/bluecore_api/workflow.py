import datetime
import logging
import os

import httpx

logger = logging.getLogger(__name__)

AIRFLOW_USER = os.environ.get("AIRFLOW_WWW_USER_USERNAME")
AIRFLOW_PASSWORD = os.environ.get("AIRFLOW_WWW_USER_PASSWORD")
AIRFLOW_INTERNAL_URL = os.environ.get("AIRFLOW_INTERNAL_URL").rstrip("/")


async def create_batch_from_uri(uri: str, user_uid: str | None = None) -> str:
    """
    uri: Start an Airflow DAG run to process data at a given URI. Returns the ID
         for the created DAG Run. A URI can have https, http, s3 or file protocol.
    user_uid: Keycloak subject/UID of the caller (optional). When provided, it will
              be available to the DAG as dag_run.conf["user_uid"].
    """

    token = await get_token()

    url = f"{AIRFLOW_INTERNAL_URL}/api/v2/dags/resource_loader/dagRuns"
    now = datetime.datetime.now(tz=datetime.UTC).isoformat()

    # Put the UID into the DAG run's conf so tasks can read it
    conf = {"file": uri, "user_uid": user_uid}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json={"logical_date": now, "conf": conf},
            )
            resp.raise_for_status()
            job_id = resp.json().get("dag_run_id")
        except httpx.HTTPError as e:
            logger.error(e)
            if resp.status_code == 401:
                raise WorkflowError("Invalid credentials for Bluecore Workflow API")
            else:
                raise WorkflowError(f"Bluecore Workflow API at {url} is unavailable.")

        return job_id


async def export_instance(
    user_uid: str, instance_uri: str, local_id: str | None = None
) -> str:
    """
    Triggers the monitor_export_api DAG run that exports the Instance and Work to
    institution's LSP based on the user's group.

    instance_uri: Blue Core Instance URI.
    local_id: Optional institution-local identifier (e.g. an HRID, or another
              institution's equivalent) of an existing catalog record to overlay,
              instead of resolving the target record from instance_uri alone.
    user_uid: Keycloak subject/UID
    """
    token = await get_token()

    url = f"{AIRFLOW_INTERNAL_URL}/api/v2/dags/monitor_institutions_exports/dagRuns"
    now = datetime.datetime.now(tz=datetime.UTC).isoformat()

    # NOTE: the "local_id" conf key is provisional and needs to be confirmed against
    # (or coordinated with) the monitor_institutions_exports DAG definition in
    # bluecore-workflows, which today only reads "resource" from conf. "resource"
    # is always present; "local_id" is present only when an overlay target
    # identifier was submitted, otherwise it's sent as null.
    conf = {"resource": instance_uri, "local_id": local_id, "user": user_uid}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json={"logical_date": now, "conf": conf},
            )
            resp.raise_for_status()
            job_id = resp.json().get("dag_run_id")
        except httpx.HTTPError as e:
            logger.error(e)
            match resp.status_code:
                case 401:
                    raise WorkflowError("Invalid credentials for Bluecore Workflow API")

                case _:
                    raise WorkflowError(
                        "Bluecore Workflow API at {url} is unavailable."
                    )

        return job_id


async def get_token() -> str:
    """
    Get an Access Token from Keycloak for the user we need to speak to Airflow as.
    """

    # NOTE: once apache-airflow-providers-keycloak is available we will want to
    # switch over to using that instead of using http basic auth.
    #
    # See: https://github.com/apache/airflow/issues/51362

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{AIRFLOW_INTERNAL_URL}/auth/token",
            json={"username": AIRFLOW_USER, "password": AIRFLOW_PASSWORD},
        )
        resp.raise_for_status()

        return resp.json()["access_token"]


class WorkflowError(Exception):
    pass
