"""What uses a profile: the records made with it, and other profiles' data.

A record names the template it was made with in its root
sinopia:hasResourceTemplate, as the profile's URI or as the URI of one of its
versions. Framing stores every property as a list, and CONTEXT has no term for
this predicate, so the value is always at data[HAS_RESOURCE_TEMPLATE][0]["@id"].
"""

from collections.abc import Iterator
from typing import Any

from bluecore_models.models import Profile, ResourceBase, Version
from sqlalchemy import Select, Text, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session

HAS_RESOURCE_TEMPLATE = "http://sinopia.io/vocabulary/hasResourceTemplate"

RECORD_TYPES = ("works", "instances")

template_ref = ResourceBase.data[HAS_RESOURCE_TEMPLATE][0]["@id"].astext


def referenced_by(db: Session, profile: Profile, limit: int = 5) -> list[str]:
    """URIs of resources whose data, now or in any version, mentions this profile.

    A text match, so it finds a record's hasResourceTemplate and another
    profile's nested references alike, plain or versioned. Old versions count
    because a record can be pinned to a parent template's version that nested
    this profile, even after the parent moved on. It scans the tables, which is
    fine for something as rare as deleting a profile.

    TODO: profile_relations can answer the profile half of this once it links
    versions of profiles. Today it records no link for a versioned nested
    reference, and drops a link once the parent's current data stops making it.
    """

    def mentions(data):
        text = sql_cast(data, Text)
        return or_(
            text.contains(f'"{profile.uri}"', autoescape=True),
            text.contains(f'"{profile.uri}/version/', autoescape=True),
        )

    in_a_version = (
        select(Version.id)
        .where(Version.resource_id == ResourceBase.id)
        .where(mentions(Version.data))
        .exists()
    )
    stmt = (
        select(ResourceBase.uri)
        .where(ResourceBase.id != profile.id)
        .where(or_(mentions(ResourceBase.data), in_a_version))
        .order_by(ResourceBase.id)
        .limit(limit)
    )
    return [uri for uri in db.scalars(stmt) if uri is not None]


def _with_ancestors(profile: Profile) -> list[Profile]:
    """The profile and every profile that nests it, however deeply.

    A record only names its root template, so records made with a nested
    profile are found through the templates that nest it. profile_relations
    links whole profiles, and records no link for a versioned nested reference,
    so a parent that nests this profile only by version is missed.
    """
    found = {profile.id: profile}
    todo = [profile]
    while todo:
        for parent in todo.pop().parents:
            if parent.id not in found:
                found[parent.id] = parent
                todo.append(parent)
    return list(found.values())


def _records(templates: list[Profile]) -> Select:
    names = []
    for template in templates:
        names.append(template_ref == template.uri)
        names.append(
            template_ref.startswith(f"{template.uri}/version/", autoescape=True)
        )
    return select(ResourceBase.uri, template_ref.label("version_uri")).where(
        ResourceBase.type.in_(RECORD_TYPES), or_(*names)
    )


def pinned_records(
    db: Session, profile: Profile, batch_size: int = 100
) -> Iterator[tuple[str, str, Any]]:
    """(uri, version_uri, data) of each record pinned to a version of this profile.

    Only records whose root template is this profile, not one that nests it, and
    not records naming the plain profile URI. Ordered by version, so records
    sharing one arrive together, and streamed rather than loaded at once.
    """
    stmt = (
        select(ResourceBase.uri, template_ref, ResourceBase.data)
        .where(
            ResourceBase.type.in_(RECORD_TYPES),
            template_ref.startswith(f"{profile.uri}/version/", autoescape=True),
        )
        .order_by(template_ref, ResourceBase.uri)
        .execution_options(yield_per=batch_size)
    )
    for uri, version_uri, data in db.execute(stmt):
        yield str(uri), str(version_uri), data


def find_record(db: Session, uri: str) -> tuple[str | None, Any] | None:
    """(template pointer, data) of the Work or Instance with this URI, or None.

    The pointer is None for a record that names no template.
    """
    row = db.execute(
        select(template_ref, ResourceBase.data).where(
            ResourceBase.uri == uri, ResourceBase.type.in_(RECORD_TYPES)
        )
    ).first()
    return None if row is None else (row[0], row[1])


def profile_usage(db: Session, profile: Profile, limit: int, offset: int) -> dict:
    """The records made with this profile, or with any profile that nests it.

    Each record comes with the template pointer it carries, and versions counts
    records by that pointer. For a nested profile those are its parents' URIs
    and versions, since that is all a record names. A pointer that is a plain
    profile URI has no version, so it is reported as None.
    """
    records = _records(_with_ancestors(profile)).subquery()
    instance_count = db.scalar(select(func.count()).select_from(records)) or 0

    pointers = db.execute(
        select(records.c.version_uri, func.count())
        .group_by(records.c.version_uri)
        .order_by(records.c.version_uri)
    ).all()
    versions = [
        {
            "version_uri": None if "/version/" not in pointer else pointer,
            "instance_count": count,
        }
        for pointer, count in pointers
    ]

    page = db.execute(
        select(records.c.uri, records.c.version_uri)
        .order_by(records.c.uri)
        .limit(limit)
        .offset(offset)
    ).all()
    instances = [
        {
            "uri": uri,
            "version_uri": None if "/version/" not in pointer else pointer,
        }
        for uri, pointer in page
    ]
    return {
        "instance_count": instance_count,
        "versions": versions,
        "instances": instances,
    }
