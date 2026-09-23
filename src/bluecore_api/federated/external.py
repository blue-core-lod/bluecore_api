"""GET /external/resources -- fetch an external record for editing.

The copy path. A cataloger picks a record from a federated search result and
the editor loads it; nothing is written to Blue Core until they save. That is
the whole point of federating rather than bulk loading: a record becomes a Blue
Core row when a human commits to it, not when someone looks at it.

Going through the API rather than letting the browser fetch id.loc.gov
directly (its CORS headers would allow that) buys the three things the spike
needs: one identifiable client instead of one per cataloger's IP, a place to
cache and rate-limit, and a place to answer "do we already hold a copy of
this?" before the copy is made.
"""

import logging
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

import httpx
from bluecore_models.models import Hub, Instance, ResourceBase, Work
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from bluecore_api.constants import CONTEXT_URL
from bluecore_api.database import get_db
from bluecore_api.derived_from import find_by_derived_from, uri_variants
from bluecore_api.federated import metrics
from bluecore_api.federated.cache import cached
from bluecore_api.federated.config import allowed_external_hosts
from bluecore_api.federated.http import client_for
from bluecore_api.schemas.external import ExternalResourceSchema

logger = logging.getLogger(__name__)

endpoints = APIRouter()

# The segment id.loc.gov uses for each kind of resource, and the model whose
# framing produces the shape the editor expects.
MODELS: dict[str, tuple[type[ResourceBase], str]] = {
    "works": (Work, "works"),
    "instances": (Instance, "instances"),
    "hubs": (Hub, "hubs"),
}

# Properties that point at the counterpart record. Framing embeds the whole
# counterpart; see prune_counterparts.
COUNTERPART_PROPERTIES = ("hasInstance", "instanceOf")


def check_host(uri: str) -> None:
    """Refuse anything outside the allow-list.

    This endpoint fetches a URL supplied by the caller, so without the check it
    is an open relay into whatever the API container can reach.
    """
    parsed = urlparse(uri)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400, detail=f"Unsupported URI scheme: {parsed.scheme!r}."
        )
    allowed = allowed_external_hosts()
    if parsed.hostname not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{parsed.hostname} is not a configured external source. "
                f"Allowed: {', '.join(sorted(allowed))}."
            ),
        )


def kind_of(uri: str) -> tuple[type[ResourceBase], str]:
    """Work out what an id.loc.gov resource URI describes, from its path."""
    for segment, model in MODELS.items():
        if f"/{segment}/" in urlparse(uri).path:
            return model
    raise HTTPException(
        status_code=400,
        detail=(
            "Could not tell what kind of resource that URI describes. "
            f"Expected one of: {', '.join(MODELS)}."
        ),
    )


def jsonld_url(uri: str) -> str:
    """id.loc.gov 303-redirects a resource URI to its JSON-LD, but asking for
    it directly saves a round trip.

    Note .cbd.jsonld is not an option here: it exists for instances only, and a
    work returns 403 for it.
    """
    return uri if uri.endswith(".jsonld") else f"{uri}.jsonld"


def prune_counterparts(data: dict[str, Any]) -> dict[str, Any]:
    """Reduce an embedded Work or Instance to a bare reference.

    LC's JSON-LD for a work carries its instance (and vice versa) as a fully
    described, typed node. The editor strips the Work-Instance link when
    copying, so that description would land in unusedRDF and be merged back
    into the save -- where it is still typed, and save_graph would mint a Blue
    Core Instance nobody asked for. Copying one record should create one
    record; copying the pair is a feature someone can ask for deliberately.
    """
    pruned = deepcopy(data)
    for property_ in COUNTERPART_PROPERTIES:
        nodes = pruned.get(property_)
        if not isinstance(nodes, list):
            continue
        pruned[property_] = [
            {"@id": node["@id"]}
            for node in nodes
            if isinstance(node, dict) and node.get("@id")
        ]
    return pruned


def subject_of(payload: Any, uri: str) -> str:
    """The URI the graph actually describes.

    id.loc.gov publishes http:// URIs inside its records but redirects
    browsers to https://, so a caller can perfectly reasonably hand us the
    other form. Framing around a subject that does not appear in the graph
    silently yields an empty document, so resolve it here instead.
    """
    nodes = payload if isinstance(payload, list) else [payload]
    ids = {
        node.get("@id") for node in nodes if isinstance(node, dict) and node.get("@id")
    }
    for variant in uri_variants(uri):
        if variant in ids:
            return variant
    raise HTTPException(
        status_code=502,
        detail=f"The record fetched for {uri} does not describe it.",
    )


def frame_for_editing(uri: str, payload: Any) -> tuple[str, dict[str, Any], str]:
    """Turn an external graph into the compact shape Blue Core serves.

    Constructing an unsaved model instance is enough: bluecore-models frames
    JSON-LD in an attribute-set event, not on flush, so this touches no
    database and no session. Note the constructor argument order matters --
    uri has to be set before data.
    """
    model, type_ = kind_of(uri)
    uri = subject_of(payload, uri)
    try:
        framed = model(uri=uri, data=payload).data
    except Exception as error:
        logger.warning("Could not frame %s: %s", uri, error)
        raise HTTPException(
            status_code=502,
            detail="The external record could not be read as BIBFRAME.",
        ) from error

    if not isinstance(framed, dict):
        raise HTTPException(
            status_code=502, detail="The external record was not a single resource."
        )

    data = prune_counterparts(framed)
    data["@context"] = CONTEXT_URL
    return uri, data, type_


async def fetch_jsonld(http: httpx.AsyncClient, uri: str) -> Any:
    url = jsonld_url(uri)

    async def get() -> Any:
        response = await http.get(url, headers={"Accept": "application/ld+json"})
        response.raise_for_status()
        return response.json()

    try:
        return await cached(url, get)
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        if status == 404:
            raise HTTPException(
                status_code=404, detail=f"{uri} was not found at its source."
            ) from error
        raise HTTPException(
            status_code=502, detail=f"The external source returned HTTP {status}."
        ) from error
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=504, detail="The external source could not be reached."
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=502, detail="The external source sent something unreadable."
        ) from error


@endpoints.get(
    "/external/resources",
    response_model=ExternalResourceSchema,
    operation_id="external_resource",
)
async def external_resource(
    request: Request,
    uri: str = Query(description="Resource URI at an allow-listed external source."),
    db: Session = Depends(get_db),
) -> ExternalResourceSchema:
    """Fetch an external BIBFRAME record, framed as Blue Core would serve it.

    Nothing is persisted. `bluecore_uri` says whether Blue Core already holds a
    copy derived from this record, so a client can offer to open that instead
    of making a second one.
    """
    check_host(uri)
    # Before any network call: an unsupported URI should not cost a fetch.
    kind_of(uri)

    async with client_for(request.app) as http:
        payload = await fetch_jsonld(http, uri)

    subject, data, type_ = frame_for_editing(uri, payload)
    held = find_by_derived_from(db, [subject], type_)
    metrics.record_fetch(subject, already_held=subject in held)

    return ExternalResourceSchema(
        uri=subject,
        type=type_,
        source=urlparse(uri).hostname or "",
        data=data,
        bluecore_uri=held.get(subject),
    )
