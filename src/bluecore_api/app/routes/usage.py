import re
from collections import Counter
from collections.abc import Iterator

from bluecore_models.models import (
    BibframeOtherResources,
    Instance,
    OtherResource,
    ResourceBase,
    Work,
)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bluecore_api.app.utils.jsonld import model_data_as_dict
from bluecore_api.app.views.search_display import resource_title
from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import UsageSchema, UsageWorkSchema

endpoints = APIRouter()

# How many Works are read for what they use the entity as. Counts of Works and
# Instances are always complete; past this, used_as and roles are a sample.
SCAN_LIMIT = 2000
RECENT_WORKS = 10

# Properties that say how a Work relates to itself or its record, not how it
# uses an entity.
NOT_USES = {"@id", "@type", "@context", "hasInstance", "adminMetadata"}

LC_NAME = re.compile(
    r"^https?://id\.loc\.gov/(?:authorities/names|rwo/agents)/([a-z]+\d+)$"
)


def equivalents(uri: str) -> list[str]:
    """
    The URIs Blue Core may store for one entity. LC names an agent by its
    authority (/authorities/names/) and by the real-world object it describes
    (/rwo/agents/), and Blue Core keeps the http form id.loc.gov's data uses.
    """
    uri = uri.strip()
    if uri.startswith("https://id.loc.gov/"):
        uri = "http://" + uri.removeprefix("https://")
    match = LC_NAME.match(uri)
    if match:
        lccn = match.group(1)
        return [
            f"http://id.loc.gov/authorities/names/{lccn}",
            f"http://id.loc.gov/rwo/agents/{lccn}",
        ]
    return [uri]


def _ids(value: object) -> Iterator[str]:
    """Every @id in a value, at any depth."""
    if isinstance(value, dict):
        if isinstance(value.get("@id"), str):
            yield value["@id"]
        for key, inner in value.items():
            if key != "@id":
                yield from _ids(inner)
    elif isinstance(value, list):
        for item in value:
            yield from _ids(item)


def _uses(data: dict, same: set[str]) -> tuple[set[str], list[str]]:
    """
    What a Work uses the entity as, by property, and the roles of the
    contributions it is the agent of.
    """
    used_as = {
        prop
        for prop, value in data.items()
        if prop not in NOT_USES and not same.isdisjoint(_ids(value))
    }
    roles = [
        role
        for contribution in data.get("contribution", [])
        if isinstance(contribution, dict)
        and not same.isdisjoint(_ids(contribution.get("agent", [])))
        for role in _ids(contribution.get("role", []))
    ]
    return used_as, roles


def _title(db: Session, work: Work) -> str:
    """
    A Work's title, or, for a Work with none of its own, one of its Instances'
    titles: what a cataloger would recognize it by, rather than its uuid.
    """
    title = resource_title(work)
    if title != str(work.uuid) and not (work.uri or "").endswith(title):
        return title
    instance = db.query(Instance).filter(Instance.work_id == work.id).first()
    return resource_title(instance) if instance is not None else title


@endpoints.get("/usage/", response_model=UsageSchema, operation_id="get_usage")
async def read_usage(uri: str, db: Session = Depends(get_db)) -> UsageSchema:
    """
    Where Blue Core uses an entity, such as an LC name or subject: how many
    Works and Instances, as what, and in which roles. Read from the links
    Blue Core keeps between each Work or Instance and the resources it uses.
    """
    if not uri.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="uri must be an http(s) URI")
    same = equivalents(uri)
    linked = (
        select(BibframeOtherResources.bibframe_resource_id)
        .join(
            OtherResource, OtherResource.id == BibframeOtherResources.other_resource_id
        )
        .where(OtherResource.uri.in_(same))
        .distinct()
    )
    records = db.scalar(
        select(func.count(Instance.id)).where(
            Instance.id.in_(linked) | Instance.work_id.in_(linked)
        )
    )
    counts = dict(
        db.execute(
            select(ResourceBase.type, func.count())
            .where(ResourceBase.id.in_(linked))
            .group_by(ResourceBase.type)
        ).all()
    )

    works = (
        db.query(Work)
        .filter(Work.id.in_(linked))
        .order_by(Work.updated_at.desc())
        .limit(SCAN_LIMIT)
        .all()
    )
    used_as: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    for work in works:
        props, work_roles = _uses(model_data_as_dict(work.data), set(same))
        used_as.update(props)
        roles.update(work_roles)

    recent = works[:RECENT_WORKS]
    instance_counts = dict(
        db.execute(
            select(Instance.work_id, func.count())
            .where(Instance.work_id.in_([work.id for work in recent]))
            .group_by(Instance.work_id)
        ).all()
    )
    return UsageSchema(
        uri=uri,
        equivalents=same,
        works=counts.get("works", 0),
        instances=counts.get("instances", 0),
        records=records or 0,
        used_as=dict(used_as.most_common()),
        roles=dict(roles.most_common()),
        recent_works=[
            UsageWorkSchema(
                uri=work.uri,
                title=_title(db, work),
                instances=instance_counts.get(work.id, 0),
            )
            for work in recent
        ],
    )
