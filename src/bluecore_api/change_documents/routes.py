from bluecore_api.change_documents.change_set import ChangeSet
from bluecore_api.change_documents.entry_point import EntryPoint
from bluecore_api.constants import BluecoreType, DEFAULT_ACTIVITY_STREAMS_PAGE_LENGTH
from bluecore_api.database import get_db
from bluecore_api.schemas.change_documents.schemas import (
    ChangeSetSchema,
    EntryPointSchema,
)
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import os

page_length: int = int(
    os.getenv("ACTIVITY_STREAMS_PAGE_LENGTH", DEFAULT_ACTIVITY_STREAMS_PAGE_LENGTH)
)
host: str = os.getenv("BLUECORE_URL", "https://bcld.info").rstrip("/")

change_documents = APIRouter()


@change_documents.get(
    "/change_documents/instances/feed",
    response_model=EntryPointSchema,
    response_model_exclude_none=True,
    operation_id="get_instances_feed",
)
async def instances_entry_point(
    db: Session = Depends(get_db),
) -> EntryPointSchema:
    return EntryPoint(
        db=db,
        bc_type=BluecoreType.INSTANCES,
        host=host,
        page_length=page_length,
    )


@change_documents.get(
    "/change_documents/instances/page/{id}",
    response_model=ChangeSetSchema,
    response_model_exclude_none=True,
    operation_id="get_instances_change_set",
)
async def instances_change_set(
    id: int,
    db: Session = Depends(get_db),
) -> ChangeSetSchema:
    return ChangeSet(
        db=db,
        bc_type=BluecoreType.INSTANCES,
        id=id,
        host=host,
        page_length=page_length,
    )


@change_documents.get(
    "/change_documents/works/feed",
    response_model=EntryPointSchema,
    response_model_exclude_none=True,
    operation_id="get_instance_feed",
)
async def works_entry_point(
    db: Session = Depends(get_db),
) -> EntryPointSchema:
    return EntryPoint(
        db=db,
        bc_type=BluecoreType.WORKS,
        host=host,
        page_length=page_length,
    )


@change_documents.get(
    "/change_documents/works/page/{id}",
    response_model=ChangeSetSchema,
    response_model_exclude_none=True,
    operation_id="get_works_change_set",
)
async def works_change_set(
    id: int,
    db: Session = Depends(get_db),
) -> ChangeSetSchema:
    return ChangeSet(
        db=db,
        bc_type=BluecoreType.WORKS,
        id=id,
        host=host,
        page_length=page_length,
    )
