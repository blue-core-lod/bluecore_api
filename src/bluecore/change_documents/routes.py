from bluecore.change_documents.activity_streams_generator import (
    ActivityStreamsGenerator,
    get_activity_streams_generator,
)
from bluecore.constants import BluecoreType
from bluecore.database import get_db
from bluecore.schemas.change_documents.schemas import (
    ChangeSetSchema,
    EntryPointSchema,
)
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

change_documents = APIRouter()


@change_documents.get(
    "/change_documents/instances/feed",
    response_model=EntryPointSchema,
    response_model_exclude_none=True,
)
async def instances_entry_point(
    generator: ActivityStreamsGenerator = Depends(get_activity_streams_generator),
    db: Session = Depends(get_db),
) -> EntryPointSchema:
    return generator.entry_point(
        db=db,
        bc_type=BluecoreType.INSTANCES,
    )


@change_documents.get(
    "/change_documents/instances/page/{id}",
    response_model=ChangeSetSchema,
    response_model_exclude_none=True,
)
async def instances_change_set(
    id: int,
    generator: ActivityStreamsGenerator = Depends(get_activity_streams_generator),
    db: Session = Depends(get_db),
) -> ChangeSetSchema:
    return generator.change_set(
        id=id,
        db=db,
        bc_type=BluecoreType.INSTANCES,
    )


@change_documents.get(
    "/change_documents/works/feed",
    response_model=EntryPointSchema,
    response_model_exclude_none=True,
)
async def works_entry_point(
    generator: ActivityStreamsGenerator = Depends(get_activity_streams_generator),
    db: Session = Depends(get_db),
) -> EntryPointSchema:
    return generator.entry_point(
        db=db,
        bc_type=BluecoreType.WORKS,
    )


@change_documents.get(
    "/change_documents/works/page/{id}",
    response_model=ChangeSetSchema,
    response_model_exclude_none=True,
)
async def works_change_set(
    id: int,
    generator: ActivityStreamsGenerator = Depends(get_activity_streams_generator),
    db: Session = Depends(get_db),
) -> ChangeSetSchema:
    return generator.change_set(
        id=id,
        db=db,
        bc_type=BluecoreType.WORKS,
    )
