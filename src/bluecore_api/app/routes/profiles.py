import json
import os
from uuid import uuid4

from bluecore_models.models import Profile
from bluecore_models.utils.graph import load_jsonld, replace_uri
from fastapi import APIRouter, Depends, HTTPException
from rdflib import RDF, Namespace, URIRef
from sqlalchemy.orm import Session

from bluecore_api.constants import READ_ONLY_ROLES, KeycloakRole
from bluecore_api.database import get_db
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)
from bluecore_api.schemas.schemas import (
    ProfileCreateSchema,
    ProfileSchema,
    ProfileUpdateSchema,
)

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")

SINOPIA = Namespace("http://sinopia.io/vocabulary/")

endpoints = APIRouter()


def _mint_resource_template(data, minted_uri: str):
    """Make the minted URI the subject of the Profile's ResourceTemplate.

    A Profile is JSON-LD with one node typed `sinopia:ResourceTemplate` whose
    @id identifies it; that @id may be empty, relative, or minted on another
    server. Re-home that node -- every triple on it, plus any references to it --
    onto the URI we just minted, dropping any pre-existing ResourceTemplate
    subject.
    """
    graph = load_jsonld(data)
    minted = URIRef(minted_uri)
    for old in set(graph.subjects(RDF.type, SINOPIA.ResourceTemplate)):
        replace_uri(graph, old, minted)
    # Guarantee the assertion exists even when the data arrived without one.
    graph.add((minted, RDF.type, SINOPIA.ResourceTemplate))
    # Serialize as expanded JSON-LD (a list of nodes with full-URI keys), not
    # compacted with a @context: sinopia_editor parses profiles by hand
    # (hit.data.map, full-URI predicate lookups) and does not honor a @context.
    return json.loads(graph.serialize(format="json-ld"))


def _generate_links(slice_size: int, limit: int, offset: int) -> dict[str, str]:
    bluecore_url = BLUECORE_URL.rstrip("/")
    links = {"first": f"{bluecore_url}/api/profiles/?limit={limit}&offset=0"}
    if offset > 0:
        links["prev"] = (
            f"{bluecore_url}/api/profiles/?limit={limit}&offset={max([offset - limit, 0])}"
        )
    if not slice_size < limit:
        links["next"] = (
            f"{bluecore_url}/api/profiles/?limit={limit}&offset={limit + offset}"
        )
    return links


@endpoints.get("/profiles/", operation_id="get_profiles")
async def read_profiles(
    uri: str | None = None,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    Search for an existing profile by uri, or return a slice of profiles
    with limit and offset.
    """
    if uri:
        db_profile = db.query(Profile).filter(Profile.uri == uri).first()
        if not db_profile:
            raise HTTPException(
                status_code=404, detail=f"Profile with uri {uri} not found"
            )
        return db_profile
    db_profiles = db.query(Profile).limit(limit).offset(offset).all()
    total = db.query(Profile).count()
    return {
        "profiles": db_profiles,
        "total": total,
        "links": _generate_links(len(db_profiles), limit, offset),
    }


@endpoints.get(
    "/profiles/{profile_uuid}",
    response_model=ProfileSchema,
    operation_id="get_profile",
)
async def read_profile(profile_uuid: str, db: Session = Depends(get_db)):
    db_profile = db.query(Profile).filter(Profile.uuid == profile_uuid).first()
    if db_profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_uuid} not found")
    return db_profile


@endpoints.post(
    "/profiles/",
    response_model=ProfileSchema,
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    status_code=201,
    operation_id="new_profile",
)
async def create_profile(profile: ProfileCreateSchema, db: Session = Depends(get_db)):
    profile_uuid = uuid4()
    bluecore_url = BLUECORE_URL.rstrip("/")
    minted_uri = f"{bluecore_url}/profiles/{profile_uuid}"
    db_profile = Profile(
        uuid=profile_uuid,
        uri=minted_uri,
        data=_mint_resource_template(json.loads(profile.data), minted_uri),
    )
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return db_profile


@endpoints.put(
    "/profiles/{profile_uuid}",
    response_model=ProfileSchema,
    dependencies=[Depends(BCP(KeycloakRole.UPDATE, READ_ONLY_ROLES))],
    operation_id="update_profile",
)
async def update_profile(
    profile_uuid: str,
    profile: ProfileUpdateSchema,
    db: Session = Depends(get_db),
):
    db_profile = db.query(Profile).filter(Profile.uuid == profile_uuid).first()
    if db_profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_uuid} not found")
    if profile.data is not None:
        db_profile.data = json.loads(profile.data)
    db.commit()
    db.refresh(db_profile)
    return db_profile
