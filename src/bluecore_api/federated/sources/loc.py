"""id.loc.gov, via its suggest2 API.

Three things about suggest2 that the obvious reading gets wrong, all verified
against the live service on 2026-09-22 and pinned by the recorded fixtures in
tests/loc-suggest2-*.json:

1. The paging parameter is `offset`, not `start`. `start=21` is accepted and
   silently ignored -- the response still echoes "start": 1 and returns page
   one. `offset=20` returns rows 21+ and echoes "start": 20.

2. `rank` is not a relevance score. Six different works for "melville moby"
   all came back with exactly 23803; it is a static per-access-point weight.
   It is kept for ordering within this source and nothing else.

3. The query is echoed back with a trailing "*", but that is not a prefix
   match you can lean on: "moby dick*" finds 390 works while "moby dic*" finds
   none. Treat the query as opaque -- urlencode it and nothing else, and never
   put it through search.py's format_query, whose output is Postgres tsquery
   syntax (:* & <->) that would be sent literally.

There is no fuzzy matching and no did-you-mean either, so a single mistyped
character returns nothing at all.

Results are returned in suggest2's own order, which is weak for known-item
lookup -- it ranks works *about* a title above the title itself. Reordering
them locally measurably fixes most of that (see benchmarks/loc_relevance.py),
and is deliberately not done here: the weakness is upstream relevance, and
hiding it behind a client-side heuristic would make a corpus we may need to
index ourselves look better than it is.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from bluecore_api.constants import CONTEXT_URL, SearchType
from bluecore_api.federated.base import (
    FederatedQuery,
    FederatedResult,
    FederatedSearchError,
    SourceResults,
)
from bluecore_api.federated.cache import cached
from bluecore_api.federated.config import (
    loc_base_url,
    loc_directories,
    max_external_offset,
)

logger = logging.getLogger(__name__)

SOURCE_ID = "loc"
SOURCE_LABEL = "Library of Congress"

# suggest2 lives under a directory per resource type.
DIRECTORIES: dict[SearchType, str] = {
    SearchType.WORKS: "works",
    SearchType.INSTANCES: "instances",
    SearchType.HUBS: "hubs",
}

# The endpoint's own limit already caps at 100, but asking id.loc.gov for a
# hundred rows a search is the impolite direction.
MAX_COUNT = 25

# A hard ceiling on how much of id.loc.gov we hold open at once, across every
# request this process is serving. A traffic spike should queue here rather
# than arrive there all at once.
MAX_CONCURRENT_REQUESTS = 4
_egress = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


def _first_str(values: object) -> str | None:
    """suggest2 returns lists for most of `more`, but "" for an absent scalar."""
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str) and value.strip():
                return value
    elif isinstance(values, str) and values.strip():
        return values
    return None


def _strings(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [v for v in values if isinstance(v, str) and v.strip()]


def title_from(hit: dict[str, Any]) -> str:
    """A title a cataloger recognizes, out of a name/title access point.

    aLabel is an access point -- "Melville, Herman, 1819-1891. Moby-Dick, or,
    The whale". Shipping that as the title makes every LC row read as broken
    next to a Blue Core row, so strip the contributor prefix when it is there.
    The untouched access point is kept as bflc:aap regardless.
    """
    a_label = hit.get("aLabel") or hit.get("suggestLabel") or ""
    contributor = _first_str(hit.get("more", {}).get("contributors"))
    if contributor and a_label.startswith(contributor):
        rest = a_label[len(contributor) :]
        # The separator is ". " normally, but a heading that already ends in a
        # period ("Magida, Arthur J.") leaves just the space behind. Matching
        # on contributor + ". " misses every one of those.
        for separator in (". ", " "):
            if rest.startswith(separator):
                rest = rest[len(separator) :]
                break
        if rest:
            return rest

    v_label = hit.get("vLabel") or ""
    if v_label and len(v_label) < len(a_label):
        return v_label
    return a_label


def _updated_at(more: dict[str, Any]) -> datetime | None:
    """The most recent lastmod. created_at has no equivalent and stays None:
    the editor shows it as a Created column and a guess there is a lie."""
    latest = None
    for value in _strings(more.get("lastmods")):
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            logger.debug("Unparseable id.loc.gov lastmod %r", value)
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest


def _contributions(more: dict[str, Any]) -> list[dict[str, object]]:
    contributors = _strings(more.get("contributors"))
    return [
        {
            "@type": "PrimaryContribution" if i == 0 else "Contribution",
            "agent": {"@type": "Agent", "label": name},
        }
        for i, name in enumerate(contributors)
    ]


def _labelled(values: object, type_: str) -> list[dict[str, str]]:
    return [{"@type": type_, "label": v} for v in _strings(values)]


def summary_jsonld(hit: dict[str, Any]) -> dict[str, object]:
    """A BIBFRAME-shaped summary of a hit.

    This is assembled from suggest2's `more` block, NOT from LC's record. It is
    deliberately lossy and exists so the hit can render in a results table; the
    real graph comes from the resource proxy. The @type values are bare class
    names ("Work", "Text"), which is what suggest2 gives and what
    sinopia_editor's hitsToResult expects to namespace itself.
    """
    more = hit.get("more") or {}
    data: dict[str, object] = {
        "@context": CONTEXT_URL,
        "@id": hit["uri"],
        "@type": _strings(more.get("rdftypes")) or ["Work"],
        "title": [{"@type": "Title", "mainTitle": title_from(hit)}]
        + [
            {"@type": "VariantTitle", "mainTitle": t}
            for t in _strings(more.get("varianttitles"))
        ],
    }
    if aap := _first_str(more.get("aaps")) or hit.get("aLabel"):
        data["bflc:aap"] = aap
    if contributions := _contributions(more):
        data["contribution"] = contributions
    if identifiers := _strings(more.get("identifiers")):
        # The works and instances directories are LCCN-keyed; treating these as
        # Lccn is a reasonable reading of an untyped list, not a guarantee.
        data["identifiedBy"] = [{"@type": "Lccn", "value": i} for i in identifiers]
    if languages := _labelled(more.get("languages"), "Language"):
        data["language"] = languages
    if genres := _labelled(more.get("genres"), "GenreForm"):
        data["genreForm"] = genres
    if subjects := _labelled(more.get("subjects"), "Topic"):
        data["subject"] = subjects
    if dates := _strings(more.get("pubdates")):
        data["provisionActivity"] = [{"@type": "Publication", "date": d} for d in dates]
    if instance := _first_str(more.get("instance")):
        data["hasInstance"] = [{"@id": instance}]
    # Provenance, so a graph lifted out of this response still says where it
    # came from and that it is a summary rather than LC's description.
    data["adminMetadata"] = [
        {
            "@type": "AdminMetadata",
            "derivedFrom": {"@id": hit["uri"]},
            "source": {"@type": "Source", "label": "id.loc.gov suggest2"},
        }
    ]
    return data


class LibraryOfCongressSource:
    """id.loc.gov's BIBFRAME Works, Instances and Hubs."""

    id = SOURCE_ID
    label = SOURCE_LABEL
    supported_types = frozenset(SearchType)

    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    def directories_for(self, type_: SearchType) -> list[str]:
        """Which suggest2 directories one search covers.

        LOC_SEARCH_DIRECTORIES narrows this if the traffic of an all-types
        search ever matters; see federated.config.loc_directories.
        """
        if type_ is SearchType.ALL:
            configured = loc_directories()
            return [d for d in DIRECTORIES.values() if d in configured]
        return [DIRECTORIES[type_]]

    def note_for(self, type_: SearchType, directories: list[str]) -> str | None:
        if type_ is not SearchType.ALL or set(directories) == set(DIRECTORIES.values()):
            return None
        covered = ", ".join(d.capitalize() for d in directories)
        return f"{self.label} results cover {covered}."

    async def search(self, query: FederatedQuery) -> SourceResults:
        directories = self.directories_for(query.type)
        note = self.note_for(query.type, directories)

        if not query.q.strip():
            # An empty q against suggest2 is a wildcard scan of 23.8M records.
            return SourceResults(results=[], total=0, note=note)

        if not directories:
            return SourceResults(
                results=[],
                total=0,
                note=f"No {self.label} directories are configured for {query.type}.",
            )

        if query.offset > max_external_offset():
            # Paging this deep is a script, not a cataloger refining a search,
            # and it is the behaviour that gets a client blocked.
            return SourceResults(results=[], truncated=True, note=note)

        results: list[FederatedResult] = []
        total = 0
        for directory in directories:
            page = await self._search_directory(directory, query)
            results.extend(page.results)
            total += page.total or 0
        return SourceResults(
            results=results,
            total=total,
            total_is_exact=False,
            note=note,
        )

    def _url(self, directory: str) -> str:
        return f"{loc_base_url()}/resources/{directory}/suggest2/"

    def _params(self, query: FederatedQuery) -> dict[str, str | int]:
        return {
            "q": query.q,
            # The default, left-anchored, alpha-sorts and is useless for
            # "find a record to copy".
            "searchtype": "keyword",
            "count": min(query.limit, MAX_COUNT),
            "offset": query.offset,
        }

    async def _fetch(self, url: str, params: dict[str, str | int]) -> Any:
        async with _egress:
            response = await self.http.get(url, params=params)
        if response.status_code == 429:
            # Say so plainly rather than retrying: a retry doubles the load on
            # a service that has just told us to back off.
            retry_after = response.headers.get("retry-after", "")
            suffix = f" Retry after {retry_after}s." if retry_after else ""
            raise FederatedSearchError(f"{self.label} is rate limiting us.{suffix}")
        response.raise_for_status()
        return response.json()

    async def _search_directory(
        self, directory: str, query: FederatedQuery
    ) -> SourceResults:
        url = self._url(directory)
        params = self._params(query)
        try:
            payload = await cached(
                str(httpx.URL(url, params=params)),
                lambda: self._fetch(url, params),
            )
        except httpx.HTTPStatusError as error:
            raise FederatedSearchError(
                f"{self.label} returned HTTP {error.response.status_code}."
            ) from error
        except httpx.RequestError as error:
            raise FederatedSearchError(f"Could not reach {self.label}.") from error
        except ValueError as error:
            raise FederatedSearchError(
                f"{self.label} sent a response we could not read."
            ) from error

        return SourceResults(
            results=[
                self._to_result(hit, directory) for hit in payload.get("hits", [])
            ],
            total=payload.get("count", 0),
        )

    def _to_result(self, hit: dict[str, Any], directory: str) -> FederatedResult:
        if not isinstance(hit, dict) or not hit.get("uri"):
            raise FederatedSearchError(f"{self.label} sent a result with no URI.")
        more = hit.get("more") or {}
        related = {}
        if instance := _first_str(more.get("instance")):
            related["instance"] = instance
        return FederatedResult(
            source=self.id,
            source_label=self.label,
            # Left as http://, the form LC returns, because it has to match the
            # bf:derivedFrom values stored on records copied from here.
            uri=hit["uri"],
            type=directory,
            data=summary_jsonld(hit),
            updated_at=_updated_at(more),
            rank=float(hit["rank"]) if str(hit.get("rank", "")).strip() else None,
            related=related,
        )
