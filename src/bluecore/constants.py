from enum import Enum


class StringEnum(str, Enum):
    """Convinience Enum that works interchangably as string."""

    def __str__(self) -> str:
        return str.__str__(self)


class BluecoreType(StringEnum):
    """Bluecore type enum."""

    WORKS = "works"
    INSTANCES = "instances"
