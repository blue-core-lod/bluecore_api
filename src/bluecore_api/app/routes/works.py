import json
import os
from pathlib import Path

from bluecore_models.bluecore_graph import save_graph
from bluecore_models.models import Work
from bluecore_models.utils.graph import BF, load_jsonld
from bluecore_models.utils.vector_db import create_embeddings
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pymilvus import MilvusClient
from rdflib import RDF
from sqlalchemy.orm import Session

from bluecore_api.app.utils.deserializer import deserialize, request_body_openapi
from bluecore_api.app.utils.examples import WORK_EXAMPLE
from bluecore_api.app.utils.serialize.response_generator import as_html
from bluecore_api.app.utils.serializer import serialize
from bluecore_api.constants import CONTEXT_URL, READ_ONLY_ROLES, KeycloakRole
from bluecore_api.database import (
    filter_vector_result,
    get_db,
    get_session_maker,
    get_vector_client,
)
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)
from bluecore_api.schemas.schemas import (
    WorkCreateSchema,
    WorkEmbeddingSchema,
    WorkSchema,
    WorkUpdateSchema,
)

endpoints = APIRouter()

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


@endpoints.get("/works/{work_uuid}", response_model=WorkSchema, operation_id="get_work")
async def read_work(
    work_uuid: str,
    request: Request,
    expand: bool = False,
    db: Session = Depends(get_db),
) -> Response:
    uuid, format = (
        Path(work_uuid).name.split(".", 1) if "." in work_uuid else (work_uuid, None)
    )

    db_work = db.query(Work).filter(Work.uuid == uuid).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")

    resp: Response | None = serialize(db_work, expand, format, request)
    if resp:
        return resp

    # No recognized format, return the default HTML serialization
    return as_html(db_work, request)


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
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    status_code=201,
    operation_id="get_works",
    openapi_extra=request_body_openapi(WorkCreateSchema, WORK_EXAMPLE),
)
async def create_work(
    work: WorkCreateSchema = Depends(deserialize(WorkCreateSchema)),
    db: Session = Depends(get_db),
    session_maker=Depends(get_session_maker),
):
    graph = load_jsonld(json.loads(work.data))
    result_graph = save_graph(session_maker, graph, BLUECORE_URL)
    work_uri = str(next(result_graph.subjects(RDF.type, BF.Work)))
    doc = db.query(Work).filter(Work.uri == work_uri).first()
    if doc:
        doc.data["@context"] = CONTEXT_URL
    return doc


@endpoints.put(
    "/works/{work_uuid}",
    response_model=WorkSchema,
    dependencies=[Depends(BCP(KeycloakRole.UPDATE, READ_ONLY_ROLES))],
    operation_id="update_work",
    openapi_extra=request_body_openapi(WorkUpdateSchema, WORK_EXAMPLE),
)
async def update_work(
    work_uuid: str,
    work: WorkUpdateSchema = Depends(deserialize(WorkUpdateSchema)),
    db: Session = Depends(get_db),
    session_maker=Depends(get_session_maker),
):
    db_work = db.query(Work).filter(Work.uuid == work_uuid).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")

    if work.data is not None:
        graph = load_jsonld(json.loads(work.data))
        save_graph(session_maker, graph, BLUECORE_URL)
        db.refresh(db_work)
        db_work.data["@context"] = CONTEXT_URL

    return db_work


@endpoints.delete(
    "/works/{work_uuid}",
    dependencies=[Depends(BCP(KeycloakRole.UPDATE, READ_ONLY_ROLES))],
    status_code=204,
    operation_id="delete_work",
)
async def delete_work(
    work_uuid: str,
    db: Session = Depends(get_db),
):
    db_work = db.query(Work).filter(Work.uuid == work_uuid).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")
    for instance in db_work.instances:
        for rbc in instance.classes:
            db.delete(rbc)
        for bor in instance.other_resources:
            db.delete(bor)
        for version in instance.versions:
            db.delete(version)
        db.delete(instance)
    for rbc in db_work.classes:
        db.delete(rbc)
    for bor in db_work.other_resources:
        db.delete(bor)
    for version in db_work.versions:
        db.delete(version)
    db.delete(db_work)
    db.commit()
    return Response(status_code=204)


@endpoints.post(
    "/works/{work_uuid}/embeddings",
    response_model=WorkEmbeddingSchema,
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
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
