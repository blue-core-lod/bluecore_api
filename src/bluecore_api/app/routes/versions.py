from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from bluecore_models.models import Hub, Instance, ResourceBase, Version, Work
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluecore_api.constants import CONTEXT_URL
from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import (
    HubSchema,
    InstanceSchema,
    VersionListSchema,
    VersionSchema,
    WorkSchema,
)

endpoints = APIRouter()

VERSION_ID = Path(
    description=(
        "Either the integer version id or the ISO 8601 timestamp, both as "
        "returned by the versions list. Example: 42 or "
        "2026-09-14T13:26:35.238471Z"
    )
)


def format_timestamp(value: datetime) -> str:
    """
    versions.created_at is a naive column holding UTC wall-clock time. JavaScript
    parses an ISO date-time string with no offset as *local* time, so without an
    explicit Z the editor's "N hours ago" labels drift by the viewer's UTC offset.
    Microseconds are kept so the string round-trips losslessly back to lookup.
    """
    return value.replace(tzinfo=None).isoformat() + "Z"


def parse_timestamp(value: str) -> datetime:
    """Inverse of format_timestamp. Naive, to match the column."""
    try:
        return datetime.fromisoformat(value.removesuffix("Z")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid version identifier: {value}"
        )


def resource_or_404(db: Session, model: type[ResourceBase], uuid: str) -> ResourceBase:
    resource = db.execute(select(model).where(model.uuid == uuid)).scalars().first()
    if resource is None:
        raise HTTPException(
            status_code=404, detail=f"{model.__name__} {uuid} not found"
        )
    return resource


def version_list(db: Session, resource: ResourceBase) -> VersionListSchema:
    """
    Column-level select keeps data out of the query entirely,
    otherwise a resource with a lot of edits would push a large
    amount of data to the editor. order_by is set to match sinopia_editor
    Versions.jsx:setVersions(key, newVersions.reverse())
    """
    rows = db.execute(
        select(
            Version.id,
            Version.created_at,
            Version.keycloak_user_id,
            Version.keycloak_username,
        )
        .where(Version.resource_id == resource.id)
        .order_by(Version.created_at, Version.id)
    ).all()
    return VersionListSchema(
        versions=[
            VersionSchema(
                id=row.id,
                timestamp=format_timestamp(row.created_at),
                # keycloak_username is only populated for versions written
                # through the HTTP layer after it was added, so fall back to the
                # GUID rather than showing the editor a blank author.
                user=row.keycloak_username or row.keycloak_user_id,
            )
            for row in rows
        ]
    )


def version_or_404(db: Session, resource: ResourceBase, version_id: str) -> Version:
    stmt = select(Version).where(Version.resource_id == resource.id)
    """
    Resolve one version by either identifier the list endpoint hands out.
    sinopia_editor provides the `timestamp` string it was given.
    `version_id` exists for MCP and other clients, which can receive both
    fields and should prefer the integer — shorter and no format to get wrong.
    """
    if version_id.isdigit():
        stmt = stmt.where(Version.id == int(version_id))
    else:
        stmt = stmt.where(Version.created_at == parse_timestamp(version_id))
    """
    (resource_id, created_at) is not unique yet, so take the newest match on a
    deterministic order — .one() would raise a 500 on a duplicate timestamp.
    """
    version = db.execute(stmt.order_by(Version.id.desc())).scalars().first()
    if version is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version_id} not found for {resource.uri}",
        )
    return version


def version_payload(
    resource: ResourceBase, version: Version
) -> HubSchema | InstanceSchema | WorkSchema:
    data = dict(cast(dict[str, object], version.data))
    data["@context"] = CONTEXT_URL
    resource_uuid = cast(UUID | None, resource.uuid)
    if isinstance(resource, Instance):
        return InstanceSchema(
            id=resource.id,
            type=resource.type,
            uri=resource.uri,
            uuid=resource_uuid,
            data=data,
            created_at=resource.created_at,
            updated_at=version.created_at,
            work_id=resource.work_id,
        )
    if isinstance(resource, Work):
        return WorkSchema(
            id=resource.id,
            type=resource.type,
            uri=resource.uri,
            uuid=resource_uuid,
            data=data,
            created_at=resource.created_at,
            updated_at=version.created_at,
            hub_id=resource.hub_id,
        )
    return HubSchema(
        id=resource.id,
        type=resource.type,
        uri=resource.uri,
        uuid=resource_uuid,
        data=data,
        created_at=resource.created_at,
        updated_at=version.created_at,
    )


@endpoints.get(
    "/hubs/{hub_uuid}/versions",
    response_model=VersionListSchema,
    operation_id="get_hub_versions",
)
async def read_hub_versions(
    hub_uuid: str,
    db: Session = Depends(get_db),
) -> VersionListSchema:
    """List every stored version of a Hub, oldest first."""
    return version_list(db, resource_or_404(db, Hub, hub_uuid))


@endpoints.get(
    "/hubs/{hub_uuid}/version/{version_id}",
    response_model=HubSchema,
    operation_id="get_hub_version",
)
async def read_hub_version(
    hub_uuid: str,
    version_id: Annotated[str, VERSION_ID],
    db: Session = Depends(get_db),
) -> HubSchema | InstanceSchema | WorkSchema:
    """Return one historical version of a Hub as stored JSON-LD."""
    resource = resource_or_404(db, Hub, hub_uuid)
    return version_payload(resource, version_or_404(db, resource, version_id))


@endpoints.get(
    "/works/{work_uuid}/versions",
    response_model=VersionListSchema,
    operation_id="get_work_versions",
)
async def read_work_versions(
    work_uuid: str,
    db: Session = Depends(get_db),
) -> VersionListSchema:
    """List every stored version of a Work, oldest first."""
    return version_list(db, resource_or_404(db, Work, work_uuid))


@endpoints.get(
    "/works/{work_uuid}/version/{version_id}",
    response_model=WorkSchema,
    operation_id="get_work_version",
)
async def read_work_version(
    work_uuid: str,
    version_id: Annotated[str, VERSION_ID],
    db: Session = Depends(get_db),
) -> HubSchema | InstanceSchema | WorkSchema:
    """Return one historical version of a Work as stored JSON-LD."""
    resource = resource_or_404(db, Work, work_uuid)
    return version_payload(resource, version_or_404(db, resource, version_id))


@endpoints.get(
    "/instances/{instance_uuid}/versions",
    response_model=VersionListSchema,
    operation_id="get_instance_versions",
)
async def read_instance_versions(
    instance_uuid: str,
    db: Session = Depends(get_db),
) -> VersionListSchema:
    """List every stored version of an Instance, oldest first."""
    return version_list(db, resource_or_404(db, Instance, instance_uuid))


@endpoints.get(
    "/instances/{instance_uuid}/version/{version_id}",
    response_model=InstanceSchema,
    operation_id="get_instance_version",
)
async def read_instance_version(
    instance_uuid: str,
    version_id: Annotated[str, VERSION_ID],
    db: Session = Depends(get_db),
) -> HubSchema | InstanceSchema | WorkSchema:
    """Return one historical version of an Instance as stored JSON-LD."""
    resource = resource_or_404(db, Instance, instance_uuid)
    return version_payload(resource, version_or_404(db, resource, version_id))
