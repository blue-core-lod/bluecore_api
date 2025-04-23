import os
import logging

import httpx


async def create_batch_from_uri(uri: str) -> str:
    """
    Start an Airflow DAG run to process data at a given URI. Returns the ID for the created DAG Run.
    A URI can have https, http, s3 or file protocol.
    """
    bluecore_workflow_url = os.environ.get(
        "AIRFLOW_URL", "http://airflow-webserver:8080"
    )
    url = f"{bluecore_workflow_url}/api/v1/dags/process/dagRuns"

    auth = httpx.BasicAuth(
        username=os.environ.get("AIRFLOW_WWW_USER_USERNAME", ""),
        password=os.environ.get("AIRFLOW_WWW_USER_PASSWORD", ""),
    )

    async with httpx.AsyncClient(auth=auth) as client:
        try:
            resp = await client.post(url, json={"conf": {"file": uri}})
            resp.raise_for_status()
            job_id = resp.json().get("dag_run_id")
        except httpx.HTTPError as e:
            logging.error(e)
            raise WorkflowError(f"Bluecore Workflow API at {url} is unavailable.")

    return job_id


class WorkflowError(Exception):
    pass
