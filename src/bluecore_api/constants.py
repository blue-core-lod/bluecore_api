import os
from enum import Enum


class StringEnum(str, Enum):
    """Convinience Enum that works interchangably as string."""

    def __str__(self) -> str:
        return str.__str__(self)


class BluecoreType(StringEnum):
    """Bluecore type enum."""

    HUBS = "hubs"
    WORKS = "works"
    INSTANCES = "instances"


class BibframeType(StringEnum):
    """Bibframe type enum."""

    HUB = "Hub"
    WORK = "Work"
    INSTANCE = "Instance"
    ITEM = "Item"


class SearchType(StringEnum):
    """Search type enum."""

    HUBS = "hubs"
    WORKS = "works"
    INSTANCES = "instances"
    ALL = "all"


CONTEXT_URL = (
    os.environ.get("BLUECORE_URL", "https://bcld.info/").rstrip("/")
    + "/api/context.jsonld"
)
DEFAULT_ACTIVITY_STREAMS_PAGE_LENGTH = 100
DEFAULT_SEARCH_PAGE_LENGTH = 20
