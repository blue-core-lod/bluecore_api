"""Versioned profile URIs: {profile uri}/version/{versions.id}.

Each one names an exact, unchanging snapshot of a profile, and resolves at
GET /profiles/{uuid}/version/{version_id}. The API builds them so that clients
never have to. See blue-core-lod/bluecore_api#338.
"""

import re

from bluecore_models.models import Profile, Version
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluecore_api.schemas.schemas import ProfileSchema

VERSION_URI = re.compile(r"(?P<profile_uri>.+)/version/(?P<version_id>[0-9]+)")


def version_uri(profile: Profile, version_id: int) -> str:
    return f"{profile.uri}/version/{version_id}"


def latest_version_uri(db: Session, profile: Profile) -> str | None:
    """The URI of the profile's newest version, or None if none was written.

    Only the id column is selected: profile.versions would load every snapshot's
    data. Ordering by created_at alone is deterministic, because versions is
    UNIQUE (resource_id, created_at).
    """
    version_id = db.execute(
        select(Version.id)
        .where(Version.resource_id == profile.id)
        .order_by(Version.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return None if version_id is None else version_uri(profile, version_id)


def with_version_uri(db: Session, profile: Profile) -> ProfileSchema:
    """A profile as the API returns it, with the URI of its newest version."""
    schema = ProfileSchema.model_validate(profile)
    schema.version_uri = latest_version_uri(db, profile)
    return schema


def resolve_version_uri(db: Session, uri: str) -> tuple[Profile, Version]:
    """The profile and version a versioned profile URI names.

    422 if the URI isn't a versioned profile URI at all, 404 if it names a
    profile or version that isn't stored. A version id belonging to some other
    profile is a 404 too: versions.id is global, so without the resource_id
    check any version would resolve under any profile's URI.
    """
    match = VERSION_URI.fullmatch(uri)
    if match is None:
        raise HTTPException(
            status_code=422, detail=f"{uri} is not a versioned profile URI"
        )
    profile = (
        db.execute(select(Profile).where(Profile.uri == match["profile_uri"]))
        .scalars()
        .first()
    )
    if profile is None:
        raise HTTPException(
            status_code=404, detail=f"Profile {match['profile_uri']} not found"
        )
    version = (
        db.execute(
            select(Version)
            .where(Version.resource_id == profile.id)
            .where(Version.id == int(match["version_id"]))
        )
        .scalars()
        .one_or_none()
    )
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version {uri} not found")
    return profile, version
