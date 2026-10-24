import json
import os
from pathlib import Path
from typing import Annotated

from bluecore_models.bluecore_graph import save_graph
from bluecore_models.models import Work
from bluecore_models.utils.graph import BF, load_jsonld
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
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
from bluecore_api.app.utils.examples import WORK_EXAMPLE
from bluecore_api.app.utils.jsonld import with_context
from bluecore_api.app.utils.serialize.response_generator import as_html
from bluecore_api.app.utils.serializer import serialize
from bluecore_api.constants import READ_ONLY_ROLES, KeycloakRole
from bluecore_api.database import (
    get_db,
    get_session_maker,
)
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)
from bluecore_api.schemas.schemas import (
    WorkCreateSchema,
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
    operation_id="get_work_embedding",
)
async def get_work_embedding(work_uuid: str):
    raise HTTPException(status_code=501, detail="Embeddings not implemented")


@endpoints.post(
    "/works/{work_uuid}/embeddings",
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    operation_id="new_work_embedding",
    status_code=201,
)
async def create_work_embedding(work_uuid: str):
    raise HTTPException(status_code=501, detail="Embeddings not implemented")


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
    graph = load_new_resource(work.data)
    work_uri = save_new_resource(session_maker, graph, BLUECORE_URL, BF.Work)
    doc = db.query(Work).filter(Work.uri == work_uri).first()
    if doc:
        with_context(doc.data)
    return doc


@endpoints.put(
    "/works/{work_uuid}",
    response_model=WorkSchema,
    dependencies=[Depends(BCP(KeycloakRole.UPDATE, READ_ONLY_ROLES))],
    operation_id="update_work",
    openapi_extra=request_body_openapi(WorkUpdateSchema, WORK_EXAMPLE),
    responses={412: PRECONDITION_FAILED_RESPONSE},
)
async def update_work(
    work_uuid: str,
    response: Response,
    if_match: Annotated[str | None, Header(description=IF_MATCH_DESCRIPTION)] = None,
    work: WorkUpdateSchema = Depends(deserialize(WorkUpdateSchema)),
    db: Session = Depends(get_db),
    session_maker=Depends(get_session_maker),
):
    """
    Replace a Work's description. Send the ETag from the GET in If-Match to
    have the save refused with a 412 if the Work changed since it was read.

    With If-Match the row stays locked from the check through the save, which
    runs inside this request's transaction and is committed here (see
    find_for_write and session_maker_for_write).
    """
    db_work = find_for_write(db, Work, work_uuid, if_match)
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")
    check_if_match(db_work, if_match)

    if work.data is not None:
        graph = load_jsonld(json.loads(work.data))
        save_graph(
            session_maker_for_write(db, session_maker, if_match),
            graph,
            BLUECORE_URL,
            primary_class=BF.Work,
        )
        # Makes a conditional save durable and releases its row lock; a no-op
        # otherwise, as save_graph has already committed its own session.
        db.commit()
        db.refresh(db_work)
        with_context(db_work.data)

    response.headers["ETag"] = resource_etag(db_work)
    return db_work


@endpoints.delete(
    "/works/{work_uuid}",
    dependencies=[Depends(BCP(KeycloakRole.UPDATE, READ_ONLY_ROLES))],
    status_code=204,
    operation_id="delete_work",
    responses={412: PRECONDITION_FAILED_RESPONSE},
)
async def delete_work(
    work_uuid: str,
    if_match: Annotated[str | None, Header(description=IF_MATCH_DESCRIPTION)] = None,
    db: Session = Depends(get_db),
):
    """
    Delete a Work and its Instances. If-Match, when sent, is checked against
    the Work's row as locked for the delete, so a save can't slip in between.
    """
    db_work = db.query(Work).filter(Work.uuid == work_uuid).with_for_update().first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_uuid} not found")
    check_if_match(db_work, if_match)
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
