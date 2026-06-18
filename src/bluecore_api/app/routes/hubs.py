import os

import rdflib
from rdflib import RDF

from bluecore_models.bluecore_graph import save_graph
from bluecore_models.models import Hub
from bluecore_models.utils.graph import BF
from bluecore_models.utils.vector_db import create_embeddings

from pymilvus import MilvusClient

from fastapi import APIRouter, Depends, HTTPException
from fastapi_keycloak_middleware import CheckPermissions

from sqlalchemy.orm import Session

from bluecore_api.database import (
    filter_vector_result,
    get_db,
    get_session_maker,
    get_vector_client,
)
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
async def create_hub(
    hub: HubCreateSchema,
    db: Session = Depends(get_db),
    session_maker=Depends(get_session_maker),
):
    graph = rdflib.Graph()
    graph.parse(data=hub.data, format="json-ld")
    result_graph = save_graph(session_maker, graph, BLUECORE_URL)
    hub_uri = str(next(result_graph.subjects(RDF.type, BF.Hub)))
    return db.query(Hub).filter(Hub.uri == hub_uri).first()


@endpoints.put(
    "/hubs/{hub_uuid}",
    response_model=HubSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
    operation_id="update_hub",
)
async def update_hub(
    hub_uuid: str,
    hub: HubUpdateSchema,
    db: Session = Depends(get_db),
    session_maker=Depends(get_session_maker),
):
    db_hub = db.query(Hub).filter(Hub.uuid == hub_uuid).first()
    if db_hub is None:
        raise HTTPException(status_code=404, detail=f"Hub {hub_uuid} not found")

    if hub.data is not None:
        graph = rdflib.Graph()
        graph.parse(data=hub.data, format="json-ld")
        save_graph(session_maker, graph, BLUECORE_URL)
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
