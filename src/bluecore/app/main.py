import os
import sys

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from typing import Dict, Any

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

from bluecore_models.models import Instance, ResourceBase, Version, Work

app = FastAPI()

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
engine = create_engine(DATABASE_URL)
session_maker = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
    db_instance = Instance(
        data=instance.data, uri=instance.uri, work_id=instance.work_id
    )
    db.add(db_instance)
    db.commit()
    db.refresh(db_instance)
    return db_instance


@app.get("/instances/{instance_id}", response_model=InstanceSchema)
async def read_instance(instance_id: int, db: Session = Depends(get_db)):
    db_instance = db.query(Instance).filter(Instance.id == instance_id).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    return db_instance


@app.put("/instances/{instance_id}", response_model=InstanceSchema)
async def update_instance(
    instance_id: int, instance: InstanceUpdateSchema, db: Session = Depends(get_db)
):
    db_instance = db.query(Instance).filter(Instance.id == instance_id).first()
    if db_instance is None:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")

    # Update fields if they are provided
    if instance.data is not None:
        db_instance.data = instance.data
    if instance.uri is not None:
        db_instance.uri = instance.uri
    if instance.work_id is not None:
        db_instance.work_id = instance.work_id

    db.commit()
    db.refresh(db_instance)
    return db_instance


@app.post("/works/", response_model=WorkSchema, status_code=201)
async def create_work(work: WorkCreateSchema, db: Session = Depends(get_db)):
    db_work = Work(data=work.data, uri=work.uri)
    db.add(db_work)
    db.commit()
    db.refresh(db_work)
    return db_work


@app.get("/works/{work_id}", response_model=WorkSchema)
async def read_work(work_id: int, db: Session = Depends(get_db)):
    db_work = db.query(Work).filter(Work.id == work_id).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_id} not found")
    return db_work


@app.put("/works/{work_id}", response_model=WorkSchema)
async def update_work(
    work_id: int, work: WorkUpdateSchema, db: Session = Depends(get_db)
):
    db_work = db.query(Work).filter(Work.id == work_id).first()
    if db_work is None:
        raise HTTPException(status_code=404, detail=f"Work {work_id} not found")

    # Update fields if they are provided
    if work.data is not None:
        db_work.data = work.data
    if work.uri is not None:
        db_work.uri = work.uri

    db.commit()
    db.refresh(db_work)
    return db_work


# Where should we store constants?
# PAGE_LENGTH: int = 100
PAGE_LENGTH: int = 1
# Fix host for real value
HOST = "http://127.0.0.1:3000"


@app.get(
    "/change_documents/works/activitystreams/feed",
    response_model=ActivityStreamsEntryPointSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def works_activity_streams_feed(
    id: int = 0, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    total = (
        db.query(func.count(Version.id))
        .join(ResourceBase)
        .filter(ResourceBase.type == "works")
        .scalar()
    )
    return {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://emm-spec.org/1.0/context.json",
        ],
        "summary": "Bluecore",
        "type": "OrderedCollection",
        "id": f"{HOST}/change_documents/works/activitystreams/feed",
        "totalItems": total,
        "first": {
            "id": f"{HOST}/change_documents/works/activitystreams/page/1",
            "type": "OrderedCollectionPage",
        },
        "last": {
            "id": f"{HOST}/change_documents/works/activitystreams/page/{total/PAGE_LENGTH}",
            "type": "OrderedCollectionPage",
        },
    }


# This is not how you should populate the feed!
# Populate them 100 a page.
@app.get(
    "/change_documents/works/activitystreams/page/{id}",
    response_model=ActivityStreamsChangeSetSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def works_activity_streams_page(
    id: int = 0, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    total = (
        db.query(func.count(Version.id))
        .join(ResourceBase)
        .filter(ResourceBase.type == "works")
        .scalar()
    )
    version = db.query(Version).filter(Version.id == id).first()
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version {id} not found")

    resource = version.resource
    return generate_page_item(id, total, resource, version)


@app.get(
    "/change_documents/instances/activitystreams/feed",
    response_model=ActivityStreamsEntryPointSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def instances_activity_streams_feed(
    id: int = 0, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    total = (
        db.query(func.count(Version.id))
        .join(ResourceBase)
        .filter(ResourceBase.type == "instances")
        .scalar()
    )
    return {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://emm-spec.org/1.0/context.json",
        ],
        "summary": "Bluecore",
        "type": "OrderedCollection",
        "id": f"{HOST}/change_documents/instances/activitystreams/feed",
        "totalItems": total,
        "first": {
            "id": f"{HOST}/change_documents/instances/activitystreams/page/1",
            "type": "OrderedCollectionPage",
        },
        "last": {
            "id": f"{HOST}/change_documents/instances/activitystreams/page/{total/PAGE_LENGTH}",
            "type": "OrderedCollectionPage",
        },
    }


@app.get(
    "/change_documents/instances/activitystreams/page/{id}",
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def instances_activity_streams_page(
    id: int = 0, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    return {}


def generate_page_item(
    id: int, total: int, resource: ResourceBase, version: Version
) -> Dict[str, Any]:
    # truncate the created_at timestamp for comparison
    r_created_at = str(resource.created_at)[:-4]
    v_created_at = str(version.created_at)[:-4]
    if r_created_at == v_created_at:
        my_type = "Create"
    else:
        my_type = "Update"

    if id < total:
        next = f"{HOST}/change_documents/works/activitystreams/page/{id + 1}"
        if id > 1:
            prev = f"{HOST}/change_documents/works/activitystreams/page/{id - 1}"
        else:
            prev = None
    else:
        prev = f"{HOST}/change_documents/works/activitystreams/page/{total - 1}"
        next = None

    v_created_at = str(version.created_at)  # no truncation
    return {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://emm-spec.org/1.0/context.json",
        ],
        "type": "OrderedCollectionPage",
        "id": f"{HOST}/change_documents/works/activitystreams/page/{id}",
        "partOf": f"{HOST}/change_documents/works/activitystreams/feed",
        "prev": prev,
        "next": next,
        "orderedItems": [
            {
                "summary": f"New entity for {resource.uri}",
                "published": str(version.created_at),
                "type": my_type,
                "actor": "http://bogus.org/need_to_decide",
                "object": {
                    f"id": f"{HOST}/{resource.type}/{resource.id}",
                    "updated": str(version.created_at),
                },
            }
        ],
    }
