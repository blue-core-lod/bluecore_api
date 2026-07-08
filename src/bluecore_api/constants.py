import os
from enum import StrEnum, auto


class BluecoreType(StrEnum):
    """Bluecore type enum."""

    HUBS = auto()
    WORKS = auto()
    INSTANCES = auto()


class BibframeType(StrEnum):
    """Bibframe type enum."""

    HUB = "Hub"
    WORK = "Work"
    INSTANCE = "Instance"
    ITEM = "Item"


class KeycloakRole(StrEnum):
    """Keycloak role enum."""

    CATALOGER_READ_ONLY = "cataloger-read-only"
    CREATE = auto()
    UPDATE = auto()


READ_ONLY_ROLES = [KeycloakRole.CATALOGER_READ_ONLY.value]


class SearchType(StrEnum):
    """Search type enum."""

    HUBS = auto()
    WORKS = auto()
    INSTANCES = auto()
    ALL = auto()


CONTEXT_URL = (
    os.environ.get("BLUECORE_URL", "https://bcld.info/").rstrip("/")
    + "/api/context.jsonld"
)
DEFAULT_ACTIVITY_STREAMS_PAGE_LENGTH = 100
DEFAULT_SEARCH_PAGE_LENGTH = 20
