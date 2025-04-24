from fastapi import Depends, FastAPI, HTTPException, File, UploadFile
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Any, Dict
from uuid import uuid4

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../../")
from bluecore import workflow
from bluecore.app.change_notifications.activity_streams import ActivityStreamsGenerator
from bluecore.app.resource_manager.resource_manager import ResourceManager
from bluecore_models.models import Instance, Work
from bluecore.schemas import (
    ActivityStreamsChangeSetSchema,
    ActivityStreamsEntryPointSchema,
    BatchCreateSchema,
    BatchSchema,
    InstanceSchema,
    InstanceCreateSchema,
    InstanceUpdateSchema,
    WorkSchema,
    WorkCreateSchema,
    WorkUpdateSchema,
)

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


@app.post("/bogus_instances/{id}", response_model=InstanceSchema, status_code=201)
async def bogus_create_instance(id: int, db: Session = Depends(get_db)) -> Instance:
    data = json.dumps({"name": f"Shinwoo create instance {id}"})
    instance = InstanceCreateSchema(
        data=data,
        work_id=id,
        uri=f"https://bogus.org/instances/{id}",
    )
    return RESOURCE_MANAGER.create_instance(instance=instance, db=db)


@app.put("/bogus_instances/{instance_id}", response_model=InstanceSchema)
async def bogus_update_instance(instance_id: int, db: Session = Depends(get_db)):
    inst = db.query(Instance).filter(Instance.id == instance_id).first()
    instance = InstanceUpdateSchema(
        data=json.dumps({"name": f"Shinwoo update instance {inst.id}"}),
        work_id=inst.work_id,
    )
    return RESOURCE_MANAGER.update_instance(
        instance_id=instance_id, instance=instance, db=db
    )


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


@app.post("/bogus_works/{id}", response_model=WorkSchema, status_code=201)
async def bogus_create_work(id: int, db: Session = Depends(get_db)) -> Work:
    work: WorkCreateSchema = WorkCreateSchema(
        data=json.dumps({"name": f"Shinwoo create work {id}"}),
        uri=f"https://bogus.org/works/{id}",
    )
    return RESOURCE_MANAGER.create_work(work=work, db=db)


@app.get("/works/{work_id}", response_model=WorkSchema)
async def read_work(work_id: int, db: Session = Depends(get_db)) -> Work:
    return RESOURCE_MANAGER.read_work(work_id=work_id, db=db)


@app.put("/bogus_works/{work_id}", response_model=WorkSchema)
async def bogus_update_work(work_id: int, db: Session = Depends(get_db)) -> Work:
    data = json.dumps({"name": f"Shinwoo update work {work_id}"})
    work = WorkUpdateSchema(data=data)
    return RESOURCE_MANAGER.update_work(work_id=work_id, work=work, db=db)


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


@app.post("/batches/", response_model=BatchSchema)
async def create_batch(batch: BatchCreateSchema):
    try:
        workflow_id = await workflow.create_batch_from_uri(batch.uri)
    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))

    batch = {"uri": batch.uri, "workflow_id": workflow_id}
    return batch


@app.post("/batches/upload/", response_model=BatchSchema)
async def create_batch_file(file: UploadFile = File(...)):
    try:
        upload_dir = Path("./uploads")
        batch_file = upload_dir / str(uuid4()) / file.filename
        batch_file.parent.mkdir(parents=False, exist_ok=True)

        with batch_file.open("wb") as fh:
            while buff := file.file.read(1024 * 1024):
                fh.write(buff)

        uri = "file:{batch_file.absolute()}"
        workflow_id = await workflow.create_batch_from_uri(uri)

    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))

    batch = {"uri": str(batch_file.relative_to(upload_dir)), "workflow_id": workflow_id}
    return batch
