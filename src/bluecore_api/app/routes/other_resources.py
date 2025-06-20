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

endpoints = APIRouter()


@endpoints.get("/resources/{resource_id}", response_model=OtherResourceSchema)
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
)
async def create_instance(
    resource: OtherResourceCreateSchema, db: Session = Depends(get_db)
):
    time_now = datetime.now(UTC)
    db_other_resource = OtherResource(
        data=resource.data,
        uri=resource.uri,
        created_at=time_now,
        updated_at=time_now,
    )
    db.add(db_other_resource)
    db.commit()
    db.refresh(db_other_resource)
    return db_other_resource
