from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import (
    ResourceBaseSchema,
)
from bluecore_models.models import Instance, ResourceBase, Work
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List

endpoints = APIRouter()


@endpoints.get(
    "/search/",
    response_model=List[ResourceBaseSchema],
)
async def search(db: Session = Depends(get_db), type: str = "all", q: str = ""):
    match type:
        case "all":
            stmt = (
                select(ResourceBase)
                .where(ResourceBase.type != "other_resources")
                .limit(10)
            )
        case "works":
            stmt = select(Work).limit(10)
        case "instances":
            stmt = select(Instance).limit(10)
        case _:
            raise HTTPException(status_code=400, detail="Invalid type specified")
    results: List[ResourceBase] = []
    for entry in db.execute(stmt).scalars().all():
        results.append(entry)

    return results
