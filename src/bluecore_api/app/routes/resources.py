import sys

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from bluecore_models.models import OtherResource
from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import (
    OtherResourceSchema,
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
