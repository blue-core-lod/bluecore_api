import json
import os
from pathlib import Path

from bluecore_models.bluecore_graph import save_graph
from bluecore_models.models import Hub
from bluecore_models.utils.graph import BF, load_jsonld
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi_keycloak_middleware import CheckPermissions
from rdflib import RDF
from sqlalchemy.orm import Session

from bluecore_api.app.utils.serialize.response_generator import as_jsonld
from bluecore_api.app.utils.serializer import serialize
from bluecore_api.constants import CONTEXT_URL
from bluecore_api.database import (
    get_db,
    get_session_maker,
)
from bluecore_api.schemas.schemas import (
    HubCreateSchema,
    HubSchema,
    HubUpdateSchema,
)

endpoints = APIRouter()

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


@endpoints.get("/hubs/{hub_uuid}", response_model=HubSchema, operation_id="get_hub")
async def read_hub(
    hub_uuid: str, request: Request, expand: bool = False, db: Session = Depends(get_db)
):
    uuid, format = (
        Path(hub_uuid).name.split(".", 1) if "." in hub_uuid else (hub_uuid, None)
    )
    db_hub = db.query(Hub).filter(Hub.uuid == uuid).first()
    if db_hub is None:
        raise HTTPException(status_code=404, detail=f"Hub {hub_uuid} not found")

    # html is not supported for Hubs for now, serve jsonld when html is requested
    try:
        resp: Response | None = serialize(db_hub, expand, format, request)
        if resp:
            return resp
    except Exception as _e:
        pass

    # No recognized format, return the default JSON-LD serialization
    return as_jsonld(db_hub, expand)



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
    graph = load_jsonld(json.loads(hub.data))
    result_graph = save_graph(session_maker, graph, BLUECORE_URL)
    hub_uri = str(next(result_graph.subjects(RDF.type, BF.Hub)))
    doc = db.query(Hub).filter(Hub.uri == hub_uri).first()
    if doc:
        doc.data["@context"] = CONTEXT_URL
    return doc


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
        graph = load_jsonld(json.loads(hub.data))
        save_graph(session_maker, graph, BLUECORE_URL)
        db.refresh(db_hub)
        db_hub.data["@context"] = CONTEXT_URL

    return db_hub


