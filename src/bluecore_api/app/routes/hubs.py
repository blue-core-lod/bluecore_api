import os
import json

from datetime import datetime, UTC

from pymilvus import MilvusClient

from fastapi import APIRouter, Depends, HTTPException
from fastapi_keycloak_middleware import CheckPermissions

from sqlalchemy.orm import Session

from bluecore_models.models import Hub
from bluecore_models.utils.graph import handle_external_subject
from bluecore_models.utils.vector_db import create_embeddings

from bluecore_api.database import filter_vector_result, get_db, get_vector_client
from bluecore_api.schemas.schemas import (
    HubCreateSchema,
    HubEmbeddingSchema,
    HubSchema,
    HubUpdateSchema,
)
from bluecore_api.expansion import expand_resource_graph

endpoints = APIRouter()

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


@endpoints.get("/hubs/{hub_uuid}", response_model=HubSchema, operation_id="get_hub")
async def read_hub(hub_uuid: str, expand: bool = False, db: Session = Depends(get_db)):
    db_hub = db.query(Hub).filter(Hub.uuid == hub_uuid).first()
    if db_hub is None:
        raise HTTPException(status_code=404, detail=f"Hub {hub_uuid} not found")
    if expand:
        db_hub.data = expand_resource_graph(db_hub)
    setattr(db_hub, "is_expanded", expand)
    return db_hub


@endpoints.get(
    "/hubs/{hub_uuid}/embeddings",
    response_model=HubEmbeddingSchema,
    operation_id="get_hub_embedding",
)
async def get_embedding(
    hub_uuid: str,
    db: Session = Depends(get_db),
    vector_client: MilvusClient = Depends(get_vector_client),
):
    db_hub = db.query(Hub).filter(Hub.uuid == hub_uuid).first()

    if db_hub is None:
        raise HTTPException(status_code=404, detail=f"Hub {hub_uuid} not found")

    version = max(db_hub.versions, key=lambda version: version.created_at)

    filtered_result = filter_vector_result(vector_client, "hubs", version.id)

    return {
        "hub_id": db_hub.id,
        "version_id": version.id,
        "embedding": filtered_result,
        "hub_uri": db_hub.uri,
    }


@endpoints.post(
    "/hubs/",
    response_model=HubSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
    operation_id="create_hub",
)
async def create_hub(hub: HubCreateSchema, db: Session = Depends(get_db)):
    time_now = datetime.now(UTC)
    updated_payload = handle_external_subject(
        data=hub.data, type="hubs", bluecore_base_url=BLUECORE_URL
    )
    db_hub = Hub(
        uri=updated_payload.get("uri"),
        data=updated_payload.get("data"),
        uuid=updated_payload.get("uuid"),
        created_at=time_now,
        updated_at=time_now,
    )
    db.add(db_hub)
    db.commit()
    db.refresh(db_hub)
    return db_hub


@endpoints.put(
    "/hubs/{hub_uuid}",
    response_model=HubSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
    operation_id="update_hub",
)
async def update_hub(
    hub_uuid: str, hub: HubUpdateSchema, db: Session = Depends(get_db)
):
    db_hub = db.query(Hub).filter(Hub.uuid == hub_uuid).first()
    if db_hub is None:
        raise HTTPException(status_code=404, detail=f"Hub {hub_uuid} not found")

    if hub.data is not None:
        db_hub.data = json.loads(hub.data)

    db.commit()
    db.refresh(db_hub)
    return db_hub


@endpoints.post(
    "/hubs/{hub_uuid}/embeddings",
    response_model=HubEmbeddingSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
    operation_id="new_hub_embedding",
)
async def create_hub_embedding(
    hub_uuid: str,
    db: Session = Depends(get_db),
    vector_client=Depends(get_vector_client),
):
    db_hub = db.query(Hub).filter(Hub.uuid == hub_uuid).first()
    if db_hub is None:
        raise HTTPException(status_code=404, detail=f"Hub {hub_uuid} not found")

    version = max(db_hub.versions, key=lambda version: version.created_at)

    filtered_result = filter_vector_result(vector_client, "hubs", version.id)

    if len(filtered_result) < 1:
        create_embeddings(version, "hubs", vector_client)
        filtered_result = filter_vector_result(vector_client, "hubs", version.id)

    return {
        "hub_id": db_hub.id,
        "version_id": version.id,
        "embedding": filtered_result,
        "hub_uri": db_hub.uri,
    }
