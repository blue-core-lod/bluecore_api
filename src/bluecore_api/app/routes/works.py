import os
import rdflib

from datetime import datetime, UTC
from bluecore_api.utils.print_output import print_results

from fastapi import APIRouter, Depends, HTTPException
from fastapi_keycloak_middleware import CheckPermissions

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import Query, Request, Path


from bluecore_models.models import Work
from bluecore_models.utils.graph import frame_jsonld, handle_external_subject

from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import (
    WorkCreateSchema,
    WorkSchema,
    WorkUpdateSchema,
)

endpoints = APIRouter()

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


@endpoints.get("/works/{work_uuid}", response_model=WorkSchema)
async def read_work(
    request: Request,
    work_uuid: str = Path(
        min_length=1,
        max_length=150,
        description="Works uuid, like 'b9d1d304-5c46-48a0-84c4-4eaff67e441b'",
    ),
    db: Session = Depends(get_db),
):
    query = db.query(Work).filter(Work.uuid == work_uuid)
    query_results = query.first()  # list, so it matches `find_works`
    query_results = [query_results] if query_results else []

    print_results(query_results, request.url, query)

    if not query_results:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")

    return query_results[0]


@endpoints.get("/works/", response_model=list[WorkSchema])
async def find_works(
    request: Request,
    rdf_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=150,
        description="RDF ID, like 'https://bcld.info/works/b9d1d304-5c46-48a0-84c4-4eaff67e441b'",
    ),
    type: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
        description="RDF type, like 'Monograph'",
    ),
    db: Session = Depends(get_db),
):
    """
    Find Works by RDF @id or RDF @type.
    - Uses BTREE index for @id.
    - Uses GIN JSONPath index for @type.
    """
    query = db.query(Work)

    conditions = []
    params = {}

    if rdf_id:
        # Uses BTREE index: index_works_on_data_id
        conditions.append("(data ->> '@id') = :rdf_id")
        params["rdf_id"] = rdf_id

    if type:
        # Manually escape single quotes in value to prevent syntax error
        escaped = type.replace("'", "''")
        jp = f"""jsonb_path_exists(data, '$."@type"[*] ? (@ == "{escaped}")')"""
        conditions.append(jp)

    if conditions:
        query = query.filter(text(" AND ".join(conditions)).params(**params))

    results = query.all()
    print_results(results, request.url, query)

    return results


@endpoints.post(
    "/works/",
    response_model=WorkSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
)
async def create_work(work: WorkCreateSchema, db: Session = Depends(get_db)):
    time_now = datetime.now(UTC)
    updated_payload = handle_external_subject(
        data=work.data, type="works", bluecore_base_url=BLUECORE_URL
    )
    db_work = Work(
        data=updated_payload.get("data"),
        uri=updated_payload.get("uri"),
        uuid=updated_payload.get("uuid"),
        created_at=time_now,
        updated_at=time_now,
    )
    db.add(db_work)
    db.commit()
    db.refresh(db_work)
    return db_work


@endpoints.put(
    "/works/{work_uuid}",
    response_model=WorkSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
)
async def update_work(
    work_uuid: str, work: WorkUpdateSchema, db: Session = Depends(get_db)
):
    db_work = db.query(Work).filter(Work.uuid == work_uuid).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")

    # Update data if it is provided
    if work.data is not None:
        graph = rdflib.Graph().parse(data=work.data, format="json-ld")
        db_work.data = frame_jsonld(db_work.uri, graph)

    db.commit()
    db.refresh(db_work)
    return db_work
