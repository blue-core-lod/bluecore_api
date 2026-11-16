import json
import os
from pathlib import Path
from typing import Annotated

from bluecore_models.bluecore_graph import save_graph
from bluecore_models.models import Instance, Work
from bluecore_models.utils.graph import BF, load_jsonld
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from rdflib import RDF, URIRef
from sqlalchemy.orm import Session

from bluecore_api.app.utils.create import load_new_resource, save_new_resource
from bluecore_api.app.utils.deserializer import deserialize, request_body_openapi
from bluecore_api.app.utils.etag import (
    IF_MATCH_DESCRIPTION,
    PRECONDITION_FAILED_RESPONSE,
    check_if_match,
    find_for_write,
    resource_etag,
    session_maker_for_write,
)
from bluecore_api.app.utils.examples import INSTANCE_EXAMPLE
from bluecore_api.app.utils.jsonld import load_jsonld_from_model, with_context
from bluecore_api.app.utils.serialize.response_generator import as_html
from bluecore_api.app.utils.serializer import (
    serialize,
)
from bluecore_api.constants import READ_ONLY_ROLES, KeycloakRole
from bluecore_api.database import (
    get_db,
    get_session_maker,
)
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)
from bluecore_api.schemas.schemas import (
    InstanceCreateSchema,
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
    operation_id="get_instance_embedding",
)
async def get_instance_embedding(instance_uuid: str):
    raise HTTPException(status_code=501, detail="Embeddings not implemented")


@endpoints.post(
    "/instances/{instance_uuid}/embeddings",
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    operation_id="new_instance_embedding",
    status_code=201,
)
async def create_instance_embedding(instance_uuid: str):
    raise HTTPException(status_code=501, detail="Embeddings not implemented")


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
    graph = load_new_resource(instance.data)
    if instance.work_id is not None:
        db_work = db.query(Work).filter(Work.id == instance.work_id).first()
        if db_work is None:
            raise HTTPException(
                status_code=404, detail=f"Work {instance.work_id} not found"
            )
        graph += load_jsonld_from_model(db_work.data)
        instance_subject = next(graph.subjects(RDF.type, BF.Instance))
        graph.add((instance_subject, BF.instanceOf, URIRef(db_work.uri)))
    instance_uri = save_new_resource(session_maker, graph, BLUECORE_URL, BF.Instance)

    doc = db.query(Instance).filter(Instance.uri == instance_uri).first()

    if doc:
        with_context(doc.data)
    return doc


@endpoints.put(
    "/instances/{instance_uuid}",
    response_model=InstanceSchema,
    dependencies=[Depends(BCP(KeycloakRole.UPDATE, READ_ONLY_ROLES))],
    operation_id="update_instance",
    openapi_extra=request_body_openapi(InstanceUpdateSchema, INSTANCE_EXAMPLE),
    responses={412: PRECONDITION_FAILED_RESPONSE},
)
async def update_instance(
    instance_uuid: str,
    response: Response,
    if_match: Annotated[str | None, Header(description=IF_MATCH_DESCRIPTION)] = None,
    instance: InstanceUpdateSchema = Depends(deserialize(InstanceUpdateSchema)),
    db: Session = Depends(get_db),
    session_maker=Depends(get_session_maker),
):
    """
    Replace an Instance's description. Send the ETag from the GET in If-Match
    to have the save refused with a 412 if the Instance changed since it was
    read. The ETag covers the Instance only, not the Work it belongs to.

    With If-Match the row stays locked from the check through the save, which
    runs inside this request's transaction and is committed here (see
    find_for_write and session_maker_for_write).
    """
    db_instance = find_for_write(db, Instance, instance_uuid, if_match)
    if db_instance is None:
        raise HTTPException(
            status_code=404, detail=f"Instance {instance_uuid} not found"
        )
    check_if_match(db_instance, if_match)

    if instance.data is not None:
        graph = load_jsonld(json.loads(instance.data))
        if instance.work_id is not None:
            db_work = db.query(Work).filter(Work.id == instance.work_id).first()
            if db_work is None:
                raise HTTPException(
                    status_code=404, detail=f"Work {instance.work_id} not found"
                )
            graph += load_jsonld_from_model(db_work.data)
            instance_subject = next(graph.subjects(RDF.type, BF.Instance))
            graph.add((instance_subject, BF.instanceOf, URIRef(db_work.uri)))
        save_graph(
            session_maker_for_write(db, session_maker, if_match),
            graph,
            BLUECORE_URL,
            primary_class=BF.Instance,
        )
        # Makes a conditional save durable and releases its row lock; a no-op
        # otherwise, as save_graph has already committed its own session.
        db.commit()
        db.refresh(db_instance)

        with_context(db_instance.data)

    response.headers["ETag"] = resource_etag(db_instance)
    return db_instance


@endpoints.delete(
    "/instances/{instance_uuid}",
    dependencies=[Depends(BCP(KeycloakRole.UPDATE, READ_ONLY_ROLES))],
    status_code=204,
    operation_id="delete_instance",
    responses={412: PRECONDITION_FAILED_RESPONSE},
)
async def delete_instance(
    instance_uuid: str,
    if_match: Annotated[str | None, Header(description=IF_MATCH_DESCRIPTION)] = None,
    db: Session = Depends(get_db),
):
    """
    Delete an Instance. If-Match, when sent, is checked against the Instance's
    row as locked for the delete, so a save can't slip in between.
    """
    db_instance = (
        db.query(Instance)
        .filter(Instance.uuid == instance_uuid)
        .with_for_update()
        .first()
    )
    if db_instance is None:
        raise HTTPException(
            status_code=404, detail=f"Instance {instance_uuid} not found"
        )
    check_if_match(db_instance, if_match)
    for rbc in db_instance.classes:
        db.delete(rbc)
    for bor in db_instance.other_resources:
        db.delete(bor)
    for version in db_instance.versions:
        db.delete(version)
    db.delete(db_instance)
    db.commit()
    return Response(status_code=204)
