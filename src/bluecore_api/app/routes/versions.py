from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from bluecore_models.models import Hub, Instance, Profile, ResourceBase, Version, Work
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluecore_api.constants import CONTEXT_URL
from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import (
    HubSchema,
    InstanceSchema,
    ProfileSchema,
    VersionListSchema,
    VersionSchema,
    WorkSchema,
)

endpoints = APIRouter()

VERSION_ID = Path(
    description="The integer version id, as returned by the versions list. Example: 42"
)


def format_timestamp(value: datetime) -> str:
    """
    versions.created_at is a naive column holding UTC wall-clock time. JavaScript
    parses an ISO date-time string with no offset as *local* time, so without an
    explicit Z the editor's "N hours ago" labels drift by the viewer's UTC offset.
    """
    return value.replace(tzinfo=None).isoformat() + "Z"


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

    Ordering on created_at alone is deterministic because
    UNIQUE (resource_id, created_at) admits at most one row per pair, so the
    id tiebreaker could never break a tie. The constraint's index can also
    return rows already ordered, though Postgres usually prefers a bitmap
    scan plus a cheap sort at these row counts.
    """
    rows = db.execute(
        select(
            Version.id,
            Version.created_at,
            Version.keycloak_user_id,
            Version.keycloak_username,
        )
        .where(Version.resource_id == resource.id)
        .order_by(Version.created_at)
    ).all()
    return VersionListSchema(
        versions=[
            VersionSchema(
                id=row.id,
                timestamp=format_timestamp(row.created_at),
                # keycloak_username is only populated for versions written
                # through the HTTP layer after it was added, and non-HTTP
                # writers (batch ingest, migrations) set neither field, so fall
                # back rather than handing the editor a blank or null author.
                user=row.keycloak_username or row.keycloak_user_id or "unknown",
            )
            for row in rows
        ]
    )


def version_or_404(db: Session, resource: ResourceBase, version_id: int) -> Version:
    """
    Resolve one version by the integer id the list endpoint hands out. The
    resource_id predicate is a boundary, not an optimisation: without it any
    version id would resolve under any resource's URL.
    """
    stmt = (
        select(Version)
        .where(Version.resource_id == resource.id)
        .where(Version.id == version_id)
    )
    version = db.execute(stmt).scalars().one_or_none()
    if version is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version_id} not found for {resource.uri}",
        )
    return version


def version_payload(
    resource: ResourceBase, version: Version
) -> HubSchema | InstanceSchema | ProfileSchema | WorkSchema:
    resource_uuid = cast(UUID | None, resource.uuid)
    if isinstance(resource, Profile):
        """
        A Profile's snapshot is handed back exactly as stored: its data is
        expanded JSON-LD (a list of nodes keyed by full URI) rather than the
        framed object the resources below hold, and it carries no @context
        because sinopia_editor parses profiles by hand and does not honor one
        -- see _mint_resource_template in routes/profiles.py. Injecting a
        @context here would also mean mutating a list as if it were a dict.

        ProfileSchema has no updated_at to carry the snapshot's own timestamp,
        which matches the live GET /profiles/{uuid}; the caller already holds
        it from the list endpoint.
        """
        return ProfileSchema(
            id=resource.id,
            uuid=resource_uuid,
            uri=resource.uri,
            data=cast(dict[str, object] | list[object], version.data),
        )
    data = dict(cast(dict[str, object], version.data))
    data["@context"] = CONTEXT_URL
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
    version_id: Annotated[int, VERSION_ID],
    db: Session = Depends(get_db),
) -> HubSchema | InstanceSchema | ProfileSchema | WorkSchema:
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
    version_id: Annotated[int, VERSION_ID],
    db: Session = Depends(get_db),
) -> HubSchema | InstanceSchema | ProfileSchema | WorkSchema:
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
    version_id: Annotated[int, VERSION_ID],
    db: Session = Depends(get_db),
) -> HubSchema | InstanceSchema | ProfileSchema | WorkSchema:
    """Return one historical version of an Instance as stored JSON-LD."""
    resource = resource_or_404(db, Instance, instance_uuid)
    return version_payload(resource, version_or_404(db, resource, version_id))


@endpoints.get(
    "/profiles/{profile_uuid}/versions",
    response_model=VersionListSchema,
    operation_id="get_profile_versions",
)
async def read_profile_versions(
    profile_uuid: str,
    db: Session = Depends(get_db),
) -> VersionListSchema:
    """List every stored version of a Profile, oldest first."""
    return version_list(db, resource_or_404(db, Profile, profile_uuid))


@endpoints.get(
    "/profiles/{profile_uuid}/version/{version_id}",
    response_model=ProfileSchema,
    operation_id="get_profile_version",
)
async def read_profile_version(
    profile_uuid: str,
    version_id: Annotated[int, VERSION_ID],
    db: Session = Depends(get_db),
) -> HubSchema | InstanceSchema | ProfileSchema | WorkSchema:
    """Return one historical version of a Profile as stored JSON-LD."""
    resource = resource_or_404(db, Profile, profile_uuid)
    return version_payload(resource, version_or_404(db, resource, version_id))
