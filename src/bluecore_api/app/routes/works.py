import os
import json

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from fastapi_keycloak_middleware import CheckPermissions

from sqlalchemy.orm import Session

from bluecore_models.models import Work
from bluecore_models.utils.graph import handle_external_subject

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
        uri=updated_payload.get("uri"),
        data=updated_payload.get("data"),
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
        # TODO: some day it would be nice to not have to parse work.data as JSON
        db_work.data = json.loads(work.data)

    db.commit()
    db.refresh(db_work)
    return db_work
