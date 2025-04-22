import os
import sys

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from typing import Any, Dict, List
import math

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
PAGE_LENGTH: int = 2
# Fix host for real value
HOST = "http://127.0.0.1:3000"
BF_TYPE_INSTANCES = "instances"
BF_TYPE_WORKS = "works"


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
        .filter(ResourceBase.type == BF_TYPE_WORKS)
        .scalar()
    )
    last_page: int = math.ceil(total / PAGE_LENGTH)
    return {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://emm-spec.org/1.0/context.json",
        ],
        "summary": "Bluecore",
        "type": "OrderedCollection",
        "id": f"{HOST}/change_documents/{BF_TYPE_WORKS}/activitystreams/feed",
        "totalItems": total,
        "first": {
            "id": f"{HOST}/change_documents/{BF_TYPE_WORKS}/activitystreams/page/1",
            "type": "OrderedCollectionPage",
        },
        "last": {
            "id": f"{HOST}/change_documents/{BF_TYPE_WORKS}/activitystreams/page/{last_page}",
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
        .filter(ResourceBase.type == BF_TYPE_WORKS)
        .scalar()
    )

    query = (
        db.query(Version).join(ResourceBase).filter(ResourceBase.type == BF_TYPE_WORKS)
    )
    paginated_query = query.offset((id - 1) * PAGE_LENGTH).limit(PAGE_LENGTH).all()
    return generate_page(
        id=id, items=paginated_query, total=total, bf_type=BF_TYPE_WORKS
    )


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
        .filter(ResourceBase.type == BF_TYPE_INSTANCES)
        .scalar()
    )
    last_page: int = math.ceil(total / PAGE_LENGTH)
    return {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://emm-spec.org/1.0/context.json",
        ],
        "summary": "Bluecore",
        "type": "OrderedCollection",
        "id": f"{HOST}/change_documents/{BF_TYPE_INSTANCES}/activitystreams/feed",
        "totalItems": total,
        "first": {
            "id": f"{HOST}/change_documents/{BF_TYPE_INSTANCES}/activitystreams/page/1",
            "type": "OrderedCollectionPage",
        },
        "last": {
            "id": f"{HOST}/change_documents/{BF_TYPE_INSTANCES}/activitystreams/page/{last_page}",
            "type": "OrderedCollectionPage",
        },
    }


@app.get(
    "/change_documents/instances/activitystreams/page/{id}",
    response_model=ActivityStreamsChangeSetSchema,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def instances_activity_streams_page(
    id: int = 0, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    total = (
        db.query(func.count(Version.id))
        .join(ResourceBase)
        .filter(ResourceBase.type == BF_TYPE_INSTANCES)
        .scalar()
    )

    query = (
        db.query(Version)
        .join(ResourceBase)
        .filter(ResourceBase.type == BF_TYPE_INSTANCES)
    )
    paginated_query = query.offset((id - 1) * PAGE_LENGTH).limit(PAGE_LENGTH).all()
    return generate_page(
        id=id, items=paginated_query, total=total, bf_type=BF_TYPE_WORKS
    )


def generate_page(
    id: int,
    items: List[Version],
    total: int,
    bf_type: str,
) -> Dict[str, Any]:
    total_pages = math.ceil(total / PAGE_LENGTH)
    if id < total_pages:
        next = f"{HOST}/change_documents/{bf_type}/activitystreams/page/{id + 1}"
        if id > 1:
            prev = f"{HOST}/change_documents/{bf_type}/activitystreams/page/{id - 1}"
        else:
            prev = None
    else:
        prev = (
            f"{HOST}/change_documents/{bf_type}/activitystreams/page/{total_pages - 1}"
        )
        next = None

    return {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://emm-spec.org/1.0/context.json",
            {"bf": "http://id.loc.gov/ontologies/bibframe/"},
        ],
        "type": "OrderedCollectionPage",
        "id": f"{HOST}/change_documents/{bf_type}/activitystreams/page/{id}",
        "partOf": f"{HOST}/change_documents/{bf_type}/activitystreams/feed",
        "prev": prev,
        "next": next,
        "orderedItems": generate_ordered_items(items),
        "totalItems": len(items),
    }


def generate_ordered_items(versions: List[Version]) -> List[Dict[str, Any]]:
    # This function should generate the ordered items based on your requirements
    # For now, it returns an empty list
    ordered_items: List[Dict[str, Any]] = []
    for version in versions:
        resource = version.resource
        # truncate the created_at timestamp for comparison
        r_created_at = str(resource.created_at)[:-4]
        v_created_at = str(version.created_at)[:-4]
        if r_created_at == v_created_at:
            my_type = "Create"
        else:
            my_type = "Update"
        ordered_items.append(
            {
                "summary": f"New entity for {resource.uri}",
                "published": str(version.created_at),
                "type": my_type,
                "object": {
                    "id": f"{HOST}/{resource.type}/{resource.id}",
                    "updated": str(version.created_at),
                    "type": f"bf:{resource.type.capitalize()}",
                },
            }
        )

    return ordered_items
