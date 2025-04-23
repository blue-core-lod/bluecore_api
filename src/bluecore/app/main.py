import os
import sys

from fastapi import FastAPI, Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Any, Dict

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../../")

from bluecore.schemas import (
    ActivityStreamsChangeSetSchema,
    ActivityStreamsEntryPointSchema,
    InstanceSchema,
    InstanceCreateSchema,
    InstanceUpdateSchema,
    WorkSchema,
    WorkCreateSchema,
    WorkUpdateSchema,
)

from bluecore.app.change_notifications.activity_streams import ActivityStreamsGenerator
from bluecore.app.resource_manager.resource_manager import ResourceManager
from bluecore_models.models import Instance, Work

app = FastAPI()

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
engine = create_engine(DATABASE_URL)
session_maker = sessionmaker(autocommit=False, autoflush=False, bind=engine)
ACTIVITY_STREAMS_GENERATOR = ActivityStreamsGenerator()
RESOURCE_MANAGER = ResourceManager()


def get_db():
    db = session_maker()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
async def index():
    return {"message": "Blue Core API"}


@app.post("/instances/", response_model=InstanceSchema, status_code=201)
async def create_instance(
    instance: InstanceCreateSchema, db: Session = Depends(get_db)
) -> Instance:
    return RESOURCE_MANAGER.create_instance(instance=instance, db=db)


@app.get("/instances/{instance_id}", response_model=InstanceSchema)
async def read_instance(instance_id: int, db: Session = Depends(get_db)):
    return RESOURCE_MANAGER.read_instance(instance_id=instance_id, db=db)


@app.put("/instances/{instance_id}", response_model=InstanceSchema)
async def update_instance(
    instance_id: int, instance: InstanceUpdateSchema, db: Session = Depends(get_db)
):
    return RESOURCE_MANAGER.update_instance(
        instance_id=instance_id, instance=instance, db=db
    )


@app.post("/works/", response_model=WorkSchema, status_code=201)
async def create_work(work: WorkCreateSchema, db: Session = Depends(get_db)) -> Work:
    return RESOURCE_MANAGER.create_work(work=work, db=db)


@app.get("/works/{work_id}", response_model=WorkSchema)
async def read_work(work_id: int, db: Session = Depends(get_db)) -> Work:
    return RESOURCE_MANAGER.read_work(work_id=work_id, db=db)


@app.put("/works/{work_id}", response_model=WorkSchema)
async def update_work(
    work_id: int, work: WorkUpdateSchema, db: Session = Depends(get_db)
) -> Work:
    return RESOURCE_MANAGER.update_work(work_id=work_id, work=work, db=db)


@app.get(
    "/change_documents/works/activitystreams/feed",
    response_model=ActivityStreamsEntryPointSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def works_activity_streams_feed(
    id: int = 0, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    return ACTIVITY_STREAMS_GENERATOR.works_activity_streams_feed(db=db)


@app.get(
    "/change_documents/works/activitystreams/page/{id}",
    response_model=ActivityStreamsChangeSetSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def works_activity_streams_page(
    id: int = 0, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    return ACTIVITY_STREAMS_GENERATOR.works_activity_streams_page(id=id, db=db)


@app.get(
    "/change_documents/instances/activitystreams/feed",
    response_model=ActivityStreamsEntryPointSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def instances_activity_streams_feed(
    id: int = 0, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    return ACTIVITY_STREAMS_GENERATOR.instances_activity_streams_feed(db=db)


@app.get(
    "/change_documents/instances/activitystreams/page/{id}",
    response_model=ActivityStreamsChangeSetSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def instances_activity_streams_page(
    id: int = 0, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    return ACTIVITY_STREAMS_GENERATOR.instances_activity_streams_page(id=id, db=db)
