import os
import json

from datetime import datetime, UTC

from pymilvus import MilvusClient

from fastapi import APIRouter, Depends, HTTPException
from fastapi_keycloak_middleware import CheckPermissions

from sqlalchemy.orm import Session

from bluecore_models.models import Work
from bluecore_models.utils.graph import handle_external_subject
from bluecore_models.utils.vector_db import create_embeddings

from bluecore_api.database import filter_vector_result, get_db, get_vector_client
from bluecore_api.schemas.schemas import (
    WorkCreateSchema,
    WorkEmbeddingSchema,
    WorkSchema,
    WorkUpdateSchema,
)

endpoints = APIRouter()

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


@endpoints.get("/works/{work_uuid}", response_model=WorkSchema, operation_id="get_work")
async def read_work(work_uuid: str, db: Session = Depends(get_db)):
    db_work = db.query(Work).filter(Work.uuid == work_uuid).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")
    return db_work


@endpoints.get(
    "/works/{work_uuid}/embeddings",
    response_model=WorkEmbeddingSchema,
    operation_id="get_work_embedding",
)
async def get_embedding(
    work_uuid: str,
    db: Session = Depends(get_db),
    vector_client: MilvusClient = Depends(get_vector_client),
):
    db_work = db.query(Work).filter(Work.uuid == work_uuid).first()

    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")

    version = max(db_work.versions, key=lambda version: version.created_at)

    filtered_result = filter_vector_result(vector_client, "works", version.id)

    return {
        "work_id": db_work.id,
        "version_id": version.id,
        "embedding": filtered_result,
        "work_uri": db_work.uri,
    }


@endpoints.post(
    "/works/",
    response_model=WorkSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
    operation_id="get_works",
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
    operation_id="get_work",
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


@endpoints.post(
    "/works/{work_uuid}/embeddings",
    response_model=WorkEmbeddingSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
    operation_id="new_work_embedding",
)
async def create_work_embedding(
    work_uuid: str,
    db: Session = Depends(get_db),
    vector_client=Depends(get_vector_client),
):
    db_work = db.query(Work).filter(Work.uuid == work_uuid).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")

    version = max(db_work.versions, key=lambda version: version.created_at)

    filtered_result = filter_vector_result(vector_client, "works", version.id)

    if len(filtered_result) < 1:
        create_embeddings(version, "works", vector_client)
        filtered_result = filter_vector_result(vector_client, "works", version.id)

    return {
        "work_id": db_work.id,
        "version_id": version.id,
        "embedding": filtered_result,
        "work_uri": db_work.uri,
    }
