import json
import os
from datetime import UTC, datetime
from typing import Any

from bluecore_models.models import BibframeOtherResources, OtherResource
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from bluecore_api.constants import CONTEXT_URL, READ_ONLY_ROLES, KeycloakRole
from bluecore_api.database import get_db
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)
from bluecore_api.schemas.schemas import (
    OtherResourceCreateSchema,
    OtherResourceSchema,
    OtherResourceUpdateSchema,
)

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")

endpoints = APIRouter()


def _generate_links(slice_size: int, limit: int, offset: int) -> dict[str, str]:
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


def add_context_to_data(doc: OtherResource) -> OtherResource:
    """
    Add @context to data if it is a dictionary and does not already have @context
    """
    if isinstance(doc.data, dict):
        doc.data["@context"] = CONTEXT_URL
    return doc


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
    for doc in db_other_resources:
        add_context_to_data(doc)
    payload: dict[str, Any] = {"resources": db_other_resources, "total": total}
    payload["links"] = _generate_links(len(db_other_resources), limit, offset)
    return payload


@endpoints.get(
    "/resources/{resource_id}",
    response_model=OtherResourceSchema,
    operation_id="get_resource",
)
async def read_other_resource(resource_id: str, db: Session = Depends(get_db)):
    db_other_resource = (
        db.query(OtherResource).filter(OtherResource.id == resource_id).first()
    )
    if db_other_resource is None:
        raise HTTPException(
            status_code=404, detail=f"Other Resource {resource_id} not found"
        )
    add_context_to_data(db_other_resource)

    return db_other_resource


@endpoints.post(
    "/resources/",
    response_model=OtherResourceSchema,
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    status_code=201,
    operation_id="new_other_resource",
)
async def create_other_resource(
    resource: OtherResourceCreateSchema, db: Session = Depends(get_db)
):
    time_now = datetime.now(UTC)
    db_other_resource = OtherResource(
        uri=resource.uri,
        data=json.loads(resource.data),
        created_at=time_now,
        updated_at=time_now,
    )
    db.add(db_other_resource)
    db.commit()
    db.refresh(db_other_resource)
    add_context_to_data(db_other_resource)
    return db_other_resource


@endpoints.put(
    "/resources/{resource_id}",
    response_model=OtherResourceSchema,
    dependencies=[Depends(BCP(KeycloakRole.UPDATE, READ_ONLY_ROLES))],
    operation_id="update_other_resource",
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
    if other_resource.uri:
        db_other_resource.uri = other_resource.uri
    if other_resource.data:
        # bluecore_api #126
        db_other_resource.data = json.loads(other_resource.data)

    db.commit()
    db.refresh(db_other_resource)
    add_context_to_data(db_other_resource)
    return db_other_resource


@endpoints.delete(
    "/resources/{resource_id}",
    dependencies=[Depends(BCP(KeycloakRole.UPDATE, READ_ONLY_ROLES))],
    status_code=204,
    operation_id="delete_other_resource",
)
async def delete_other_resource(
    resource_id: str,
    db: Session = Depends(get_db),
):
    db_other_resource = (
        db.query(OtherResource).filter(OtherResource.id == resource_id).first()
    )
    if db_other_resource is None:
        raise HTTPException(
            status_code=404, detail=f"Other Resource {resource_id} not found"
        )
    for bor in (
        db.query(BibframeOtherResources)
        .filter(BibframeOtherResources.other_resource_id == db_other_resource.id)
        .all()
    ):
        db.delete(bor)
    for bor in db_other_resource.other_resources:
        db.delete(bor)
    for rbc in db_other_resource.classes:
        db.delete(rbc)
    for version in db_other_resource.versions:
        db.delete(version)
    db.delete(db_other_resource)
    db.commit()
    return Response(status_code=204)
