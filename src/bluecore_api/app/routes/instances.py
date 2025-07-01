import os
import rdflib

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException

from fastapi_keycloak_middleware import CheckPermissions

from sqlalchemy.orm import Session

from bluecore_models.utils.graph import frame_jsonld, handle_external_subject
from bluecore_models.models import Instance

from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import (
    InstanceCreateSchema,
    InstanceSchema,
    InstanceUpdateSchema,
)

endpoints = APIRouter()

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


@endpoints.get("/instances/{instance_uuid}", response_model=InstanceSchema)
async def read_instance(instance_uuid: str, db: Session = Depends(get_db)):
    db_instance = db.query(Instance).filter(Instance.uuid == instance_uuid).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    return db_instance


@endpoints.post(
    "/instances/",
    response_model=InstanceSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
)
async def create_instance(
    instance: InstanceCreateSchema, db: Session = Depends(get_db)
):
    time_now = datetime.now(UTC)
    updated_payload = handle_external_subject(
        data=instance.data, type="instances", bluecore_base_url=BLUECORE_URL
    )
    db_instance = Instance(
        data=updated_payload.get("data"),
        uri=updated_payload.get("uri"),
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
        graph = rdflib.Graph().parse(data=instance.data, format="json-ld")
        db_instance.data = frame_jsonld(db_instance.uri, graph)
    if instance.work_id is not None:
        db_instance.work_id = instance.work_id

    db.commit()
    db.refresh(db_instance)
    return db_instance
