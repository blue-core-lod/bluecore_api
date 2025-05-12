from bluecore.change_documents.entry_point import EntryPoint
from bluecore.constants import BluecoreType, DEFAULT_ACTIVITY_STREAMS_PAGE_LENGTH
from bluecore.database import get_db
from bluecore.schemas.change_documents.schemas import (
    ChangeSetSchema,
    EntryPointSchema,
)
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import os

page_length: int = int(
    os.getenv("ACTIVITY_STREAMS_PAGE_LENGTH", DEFAULT_ACTIVITY_STREAMS_PAGE_LENGTH)
)
host: str = os.getenv("ACTIVITY_STREAMS_HOST", "http://127.0.0.1:3000")

change_documents = APIRouter()


@change_documents.get(
    "/change_documents/instances/feed",
    response_model=EntryPointSchema,
    response_model_exclude_none=True,
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
)
async def instances_change_set(
    id: int,
    db: Session = Depends(get_db),
) -> ChangeSetSchema:
    return ChangeSetSchema(
        id="TBD",
        partOf="TBD",
        orderedItems=[],
    )


@change_documents.get(
    "/change_documents/works/feed",
    response_model=EntryPointSchema,
    response_model_exclude_none=True,
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
)
async def works_change_set(
    id: int,
    db: Session = Depends(get_db),
) -> ChangeSetSchema:
    return ChangeSetSchema(
        id="TBD",
        partOf="TBD",
        orderedItems=[],
    )
