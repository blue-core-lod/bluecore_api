import json
import os
from datetime import UTC, datetime

from pymilvus import MilvusClient

from bluecore_models.models import Instance
from bluecore_models.utils.graph import handle_external_subject
from bluecore_models.utils.vector_db import create_embeddings
from fastapi import APIRouter, Depends, HTTPException
from fastapi_keycloak_middleware import CheckPermissions
from sqlalchemy.orm import Session

from bluecore_api.database import filter_vector_result, get_db, get_vector_client
from bluecore_api.schemas.schemas import (
    InstanceCreateSchema,
    InstanceEmbeddingSchema,
    InstanceSchema,
    InstanceUpdateSchema,
)

endpoints = APIRouter()

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


@endpoints.get("/instances/{instance_uuid}", response_model=InstanceSchema, operation_id="get_instance")
async def read_instance(instance_uuid: str, db: Session = Depends(get_db)):
    db_instance = db.query(Instance).filter(Instance.uuid == instance_uuid).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    return db_instance


@endpoints.get(
    "/instances/{instance_uuid}/embeddings", response_model=InstanceEmbeddingSchema, operation_id="get_instance_embedding"
)
async def get_embedding(
    instance_uuid: str,
    db: Session = Depends(get_db),
    vector_client: MilvusClient = Depends(get_vector_client),
):
    db_instance = db.query(Instance).filter(Instance.uuid == instance_uuid).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    version = max(db_instance.versions, key=lambda version: version.created_at)

    filtered_result = filter_vector_result(vector_client, "instances", version.id)

    return {
        "instance_id": db_instance.id,
        "version_id": version.id,
        "embedding": filtered_result,
        "instance_uri": db_instance.uri,
    }


@endpoints.post(
    "/instances/",
    response_model=InstanceSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
    operation_id="new_instance"
)
async def create_instance(
    instance: InstanceCreateSchema, db: Session = Depends(get_db)
):
    time_now = datetime.now(UTC)
    updated_payload = handle_external_subject(
        data=instance.data, type="instances", bluecore_base_url=BLUECORE_URL
    )
    db_instance = Instance(
        uri=updated_payload.get("uri"),
        data=updated_payload.get("data"),
        work_id=instance.work_id,
        uuid=updated_payload.get("uuid"),
        created_at=time_now,
        updated_at=time_now,
    )
    db.add(db_instance)
    db.commit()
    db.refresh(db_instance)
    return db_instance


@endpoints.put(
    "/instances/{instance_uuid}",
    response_model=InstanceSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
    operation_id="update_instance"
)
async def update_instance(
    instance_uuid: str, instance: InstanceUpdateSchema, db: Session = Depends(get_db)
):
    db_instance = db.query(Instance).filter(Instance.uuid == instance_uuid).first()
    if db_instance is None:
        raise HTTPException(
            status_code=404, detail=f"Instance {instance_uuid} not found"
        )

    # Update fields if they are provided
    if instance.data is not None:
        # TODO: should instance.data be a dict instead of a JSON str?
        db_instance.data = json.loads(instance.data)
    if instance.work_id is not None:
        db_instance.work_id = instance.work_id

    db.commit()
    db.refresh(db_instance)
    return db_instance


@endpoints.post(
    "/instances/{instance_uuid}/embeddings",
    response_model=InstanceEmbeddingSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
    operation_id="new_instance_embedding"
)
async def create_instance_embedding(
    instance_uuid: str,
    db: Session = Depends(get_db),
    vector_client=Depends(get_vector_client),
):
    db_instance = db.query(Instance).filter(Instance.uuid == instance_uuid).first()
    if db_instance is None:
        raise HTTPException(
            status_code=404, detail=f"Instance {instance_uuid} not found"
        )

    version = max(db_instance.versions, key=lambda version: version.created_at)

    filtered_result = filter_vector_result(vector_client, "instances", version.id)

    if len(filtered_result) < 1:
        create_embeddings(version, "instances", vector_client)
        filtered_result = filter_vector_result(vector_client, "instances", version.id)

    return {
        "instance_id": db_instance.id,
        "instance_uri": db_instance.uri,
        "version_id": version.id,
        "embedding": filtered_result,
    }
