from enum import Enum


class StringEnum(str, Enum):
    """Convinience Enum that works interchangably as string."""

    def __str__(self) -> str:
        return str.__str__(self)


# From http://id.loc.gov/ontologies/bibframe/, these are defined as Works, Instances.
# Internally, we use the terms "works" and "instances" to refer to these types.
# We will keep them as is for now, but we may want to change them in the future.
class BFType(StringEnum):
    """Bibframe type enum."""

    WORKS = "works"
    INSTANCES = "instances"


ACTIVITY_STREAMS_PAGE_LENGTH = 100
