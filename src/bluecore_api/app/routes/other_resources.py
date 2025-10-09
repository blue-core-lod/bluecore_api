import os
import json

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from fastapi_keycloak_middleware import CheckPermissions

from sqlalchemy.orm import Session

from bluecore_models.models import OtherResource
from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import (
    OtherResourceSchema,
    OtherResourceCreateSchema,
    OtherResourceUpdateSchema,
)


BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")

endpoints = APIRouter()


def _generate_links(slice_size: int, limit: int, offset: int) -> dict:
    """
    NOTE: Current Paging strategy used by Sinopia
    """
    bluecore_url = BLUECORE_URL.rstrip("/")
    links = {"first": f"{bluecore_url}/api/resources/?limit={limit}&offset=0"}
    if offset > 0:
        links["prev"] = (
            f"{bluecore_url}/api/resources/?limit={limit}&offset={max([offset - limit, 0])}"
        )
    if not slice_size < limit:
        links["next"] = (
            f"{bluecore_url}/api/resources/?limit={limit}&offset={limit + offset}"
        )
    return links


@endpoints.get("/resources/", operation_id="get_other_resources")
async def read_other_resources(
    uri: str | None = None,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    Accessor function that searches for an existing uri or returns a
    slice of other resources with limit and offsets
    """
    if uri:
        db_other_resource = (
            db.query(OtherResource).filter(OtherResource.uri == uri).first()
        )
        if not db_other_resource:
            raise HTTPException(
                status_code=404, detail=f"Other Resource with uri {uri} not found"
            )
        return db_other_resource
    db_other_resources = db.query(OtherResource).limit(limit).offset(offset).all()
    total = db.query(OtherResource).count()
    payload = {"resources": db_other_resources, "total": total}
    payload["links"] = _generate_links(len(db_other_resources), limit, offset)
    return payload


@endpoints.get("/resources/{resource_id}", response_model=OtherResourceSchema, operation_id="get_resource")
async def read_other_resource(resource_id: str, db: Session = Depends(get_db)):
    db_other_resource = (
        db.query(OtherResource).filter(OtherResource.id == resource_id).first()
    )
    if db_other_resource is None:
        raise HTTPException(
            status_code=404, detail=f"Other Resource {resource_id} not found"
        )
    return db_other_resource


@endpoints.post(
    "/resources/",
    response_model=OtherResourceSchema,
    dependencies=[Depends(CheckPermissions(["create"]))],
    status_code=201,
    operation_id="new_other_resource"
)
async def create_other_resource(
    resource: OtherResourceCreateSchema, db: Session = Depends(get_db)
):
    time_now = datetime.now(UTC)
    db_other_resource = OtherResource(
        data=json.loads(resource.data),
        uri=resource.uri,
        is_profile=resource.is_profile,
        created_at=time_now,
        updated_at=time_now,
    )
    db.add(db_other_resource)
    db.commit()
    db.refresh(db_other_resource)
    return db_other_resource


@endpoints.put(
    "/resources/{resource_id}",
    response_model=OtherResourceSchema,
    dependencies=[Depends(CheckPermissions(["update"]))],
    operation_id="update_other_resource"
)
async def update_other_resource(
    resource_id: str,
    other_resource: OtherResourceUpdateSchema,
    db: Session = Depends(get_db),
):
    db_other_resource = (
        db.query(OtherResource).filter(OtherResource.id == resource_id).first()
    )
    if db_other_resource is None:
        raise HTTPException(
            status_code=404, detail=f"Other Resource {resource_id} not found"
        )
    if other_resource.data:
        # bluecore_api #126
        db_other_resource.data = json.loads(other_resource.data)
    if other_resource.uri:
        db_other_resource.uri = other_resource.uri
    if other_resource.is_profile is not None:
        db_other_resource.is_profile = other_resource.is_profile

    db.commit()
    db.refresh(db_other_resource)
    return db_other_resource
