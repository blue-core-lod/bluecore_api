from enum import Enum


class StringEnum(str, Enum):
    """Convinience Enum that works interchangably as string."""

    def __str__(self) -> str:
        return str.__str__(self)


class BluecoreType(StringEnum):
    """Bluecore type enum."""

    WORKS = "works"
    INSTANCES = "instances"


class BibframeType(StringEnum):
    """Bibframe type enum."""

    WORK = "Work"
    INSTANCE = "Instance"


class SearchType(StringEnum):
    """Search type enum."""

    WORKS = "works"
    INSTANCES = "instances"
    ALL = "all"


DEFAULT_ACTIVITY_STREAMS_PAGE_LENGTH = 100
DEFAULT_SEARCH_PAGE_LENGTH = 10
