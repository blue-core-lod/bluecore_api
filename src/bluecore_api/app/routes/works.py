import os
import rdflib

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from fastapi_keycloak_middleware import CheckPermissions

from sqlalchemy.orm import Session

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
async def read_work(work_uuid: str, db: Session = Depends(get_db)):
    db_work = db.query(Work).filter(Work.uuid == work_uuid).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")
    return db_work


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
