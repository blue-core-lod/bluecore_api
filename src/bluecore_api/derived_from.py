"""Finding the Blue Core resource already derived from an external record.

Provenance in Blue Core is a bf:derivedFrom assertion inside the resource's
adminMetadata -- there is no owl:sameAs, and deliberately so: a copy stops
being the same thing as its source the moment a cataloger edits it.

bluecore-models does this lookup one URI at a time while minting
(bluecore_graph._mint_all_uris). This module does it in bulk for a page of
search results, against the same index, and is the single place the JSON path
is written so the two cannot drift apart.
"""

from bluecore_models.models import ResourceBase
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# Matches the expression backing index_resource_base_on_type_derivedfrom_id
# (bluecore-models models/resource.py:83). Written the same way as the minter's
# query so the planner picks that index up here too.
DERIVED_FROM = func.jsonb_path_query_first(
    ResourceBase.data, '$.adminMetadata[*].derivedFrom."@id"'
).op("#>>")("{}")


def uri_variants(uri: str) -> list[str]:
    """Both schemes for one URI.

    id.loc.gov hands out http:// URIs in its search responses but redirects
    browsers to https://, so which form got stored depends on how the record
    arrived. Matching on one alone silently misses copies.
    """
    if uri.startswith("http://"):
        return [uri, "https://" + uri.removeprefix("http://")]
    if uri.startswith("https://"):
        return [uri, "http://" + uri.removeprefix("https://")]
    return [uri]


def find_by_derived_from(db: Session, uris: list[str]) -> dict[str, str]:
    """Map each external URI to the Blue Core URI derived from it.

    One indexed query for the whole page rather than one per row. URIs with no
    copy are simply absent from the result.

    Note the backing index is not unique and a URI can legitimately have more
    than one copy (two institutions cataloguing independently from the same
    source). This returns one of them; treating derivedFrom as an identity key
    rather than as provenance is a policy question the project has not settled.
    """
    if not uris:
        return {}

    wanted = {variant: uri for uri in uris for variant in uri_variants(uri)}
    rows = db.execute(
        select(ResourceBase.uri, DERIVED_FROM).where(DERIVED_FROM.in_(wanted))
    ).all()

    found: dict[str, str] = {}
    for bluecore_uri, source_uri in rows:
        found.setdefault(wanted[source_uri], bluecore_uri)
    return found
