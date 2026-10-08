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
    EXPORT = auto()
    UPDATE = auto()


READ_ONLY_ROLES = [KeycloakRole.CATALOGER_READ_ONLY.value]


class SearchType(StrEnum):
    """Search type enum."""

    HUBS = auto()
    WORKS = auto()
    INSTANCES = auto()
    ALL = auto()


class SearchScope(StrEnum):
    """Fields a resource search can be limited to."""

    ALL = auto()
    TITLE = auto()


#: Largest body the convert routes will read. The largest real Library of
#: Congress record measured in load testing was 21 KB, so this leaves ~50x
#: headroom for one record while keeping a hostile upload far below nginx's
#: client_max_body_size of 100m.
MAX_CONVERT_BYTES = int(os.environ.get("MAX_CONVERT_BYTES", str(1024 * 1024)))
BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")
CONTEXT_URL = BLUECORE_URL.rstrip("/") + "/api/context.jsonld"
DEFAULT_ACTIVITY_STREAMS_PAGE_LENGTH = 100
DEFAULT_SEARCH_PAGE_LENGTH = 20
