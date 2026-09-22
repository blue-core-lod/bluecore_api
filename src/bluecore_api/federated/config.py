"""Every environment variable this feature reads, in one place.

These are functions rather than the module-level constants used elsewhere in
the codebase (e.g. search.py's BLUECORE_URL) so tests can monkeypatch.setenv
them. Import-time constants freeze at first import and cannot be varied per
test, which is exactly what the source-toggle and timeout tests need to do.
"""

import os

DEFAULT_SOURCES = "bluecore,loc"
DEFAULT_LOC_BASE_URL = "https://id.loc.gov"
DEFAULT_LOC_DIRECTORIES = "works"
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_CACHE_TTL_SECONDS = 600.0
DEFAULT_MAX_EXTERNAL_OFFSET = 200
DEFAULT_ALLOWED_HOSTS = "id.loc.gov"


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def enabled_source_ids() -> list[str]:
    """Source ids to query, in the order their groups appear in the response.

    Ordered so operations can demote or drop a source without a code change.
    """
    return _csv(os.environ.get("FEDERATED_SEARCH_SOURCES", DEFAULT_SOURCES))


def loc_base_url() -> str:
    """Overridable so tests (and a local stub) don't have to match on id.loc.gov."""
    return os.environ.get("LOC_BASE_URL", DEFAULT_LOC_BASE_URL).rstrip("/")


def loc_directories() -> list[str]:
    """Which id.loc.gov resource directories a type=all search covers.

    Defaults to works alone: type=all is the editor's default, and fanning out
    to three directories would triple our traffic to a site whose robots.txt
    warns it blocks irresponsible clients. Works hits already carry their
    instance URI in more.instance.
    """
    return _csv(os.environ.get("LOC_SEARCH_DIRECTORIES", DEFAULT_LOC_DIRECTORIES))


def source_timeout_seconds() -> float:
    """Wall-clock budget for one source, enforced outside the adapter."""
    return float(
        os.environ.get("FEDERATED_SEARCH_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))
    )


def cache_ttl_seconds() -> float:
    return float(
        os.environ.get("FEDERATED_SEARCH_CACHE_TTL", str(DEFAULT_CACHE_TTL_SECONDS))
    )


def max_external_offset() -> int:
    """Past this, an external group reports truncated and makes no upstream call.

    Paging to row 5,000 of 23.8 million is never a cataloger refining a search.
    """
    return int(
        os.environ.get(
            "FEDERATED_SEARCH_MAX_EXTERNAL_OFFSET", str(DEFAULT_MAX_EXTERNAL_OFFSET)
        )
    )


def allowed_external_hosts() -> frozenset[str]:
    """Hosts the resource proxy may fetch from.

    The proxy takes a URI from the client, so without this it is an open SSRF
    relay.
    """
    return frozenset(
        _csv(os.environ.get("FEDERATED_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS))
    )
