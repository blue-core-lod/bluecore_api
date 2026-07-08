import json
import os
from pathlib import Path

from bluecore_models.bluecore_graph import save_graph
from bluecore_models.models import Instance, Work
from bluecore_models.utils.graph import BF, load_jsonld
from bluecore_models.utils.vector_db import create_embeddings
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pymilvus import MilvusClient
from rdflib import RDF, URIRef
from sqlalchemy.orm import Session

from bluecore_api.app.utils.deserializer import deserialize, request_body_openapi
from bluecore_api.app.utils.examples import INSTANCE_EXAMPLE
from bluecore_api.app.utils.serialize.response_generator import as_html
from bluecore_api.app.utils.serializer import (
    serialize,
)
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
    InstanceCreateSchema,
    InstanceEmbeddingSchema,
    InstanceSchema,
    InstanceUpdateSchema,
)

endpoints = APIRouter()

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")


@endpoints.get(
    "/instances/{instance_uuid}",
    response_model=InstanceSchema,
    operation_id="get_instance",
)
async def read_instance(
    instance_uuid: str,
    request: Request,
    expand: bool = False,
    db: Session = Depends(get_db),
) -> Response:
    uuid, format = (
        Path(instance_uuid).name.split(".", 1)
        if "." in instance_uuid
        else (instance_uuid, None)
    )
    db_instance = db.query(Instance).filter(Instance.uuid == uuid).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    resp: Response | None = serialize(db_instance, expand, format, request)
    if resp:
        return resp

    # No recognized format, return the default HTML serialization
    return as_html(db_instance, request)


@endpoints.get(
    "/instances/{instance_uuid}/embeddings",
    response_model=InstanceEmbeddingSchema,
    operation_id="get_instance_embedding",
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
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    status_code=201,
    operation_id="new_instance",
    openapi_extra=request_body_openapi(InstanceCreateSchema, INSTANCE_EXAMPLE),
)
async def create_instance(
    instance: InstanceCreateSchema = Depends(deserialize(InstanceCreateSchema)),
    db: Session = Depends(get_db),
    session_maker=Depends(get_session_maker),
):
    graph = load_jsonld(json.loads(instance.data))
    if instance.work_id is not None:
        db_work = db.query(Work).filter(Work.id == instance.work_id).first()
        if db_work is None:
            raise HTTPException(
                status_code=404, detail=f"Work {instance.work_id} not found"
            )
        graph += load_jsonld(db_work.data)
        instance_subject = next(graph.subjects(RDF.type, BF.Instance))
        graph.add((instance_subject, BF.instanceOf, URIRef(db_work.uri)))
    result_graph = save_graph(session_maker, graph, BLUECORE_URL)
    instance_uri = str(next(result_graph.subjects(RDF.type, BF.Instance)))

    doc = db.query(Instance).filter(Instance.uri == instance_uri).first()

    if doc:
        doc.data["@context"] = CONTEXT_URL
    return doc


@endpoints.put(
    "/instances/{instance_uuid}",
    response_model=InstanceSchema,
    dependencies=[Depends(BCP(KeycloakRole.UPDATE, READ_ONLY_ROLES))],
    operation_id="update_instance",
    openapi_extra=request_body_openapi(InstanceUpdateSchema, INSTANCE_EXAMPLE),
)
async def update_instance(
    instance_uuid: str,
    instance: InstanceUpdateSchema = Depends(deserialize(InstanceUpdateSchema)),
    db: Session = Depends(get_db),
    session_maker=Depends(get_session_maker),
):
    db_instance = db.query(Instance).filter(Instance.uuid == instance_uuid).first()
    if db_instance is None:
        raise HTTPException(
            status_code=404, detail=f"Instance {instance_uuid} not found"
        )

    if instance.data is not None:
        graph = load_jsonld(json.loads(instance.data))
        if instance.work_id is not None:
            db_work = db.query(Work).filter(Work.id == instance.work_id).first()
            if db_work is None:
                raise HTTPException(
                    status_code=404, detail=f"Work {instance.work_id} not found"
                )
            graph += load_jsonld(db_work.data)
            instance_subject = next(graph.subjects(RDF.type, BF.Instance))
            graph.add((instance_subject, BF.instanceOf, URIRef(db_work.uri)))
        save_graph(session_maker, graph, BLUECORE_URL)
        db.refresh(db_instance)

        db_instance.data["@context"] = CONTEXT_URL

    return db_instance


@endpoints.post(
    "/instances/{instance_uuid}/embeddings",
    response_model=InstanceEmbeddingSchema,
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    status_code=201,
    operation_id="new_instance_embedding",
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
