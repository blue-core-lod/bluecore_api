"""Normalizing inbound JSON-LD before it is parsed into a graph."""

from typing import Any, cast
from urllib.parse import urlparse

from bluecore_models.utils.graph import CONTEXT_URL as BIBFRAME_CONTEXT_URL
from bluecore_models.utils.graph import load_jsonld, terms_for
from rdflib import Graph

from bluecore_api.constants import CONTEXT_URL

_CONTEXT_PATH = urlparse(CONTEXT_URL).path


def _is_bluecore_context(reference: object) -> bool:
    """Does this @context entry point at the Bluecore context document?

    Matches the context URL of any Bluecore deployment, not just this one, so
    that data downloaded from production can be sent back to a development
    server (and vice versa).
    """
    return isinstance(reference, str) and (
        reference == CONTEXT_URL or urlparse(reference).path == _CONTEXT_PATH
    )


def _normalize(context: object) -> object:
    if _is_bluecore_context(context):
        return BIBFRAME_CONTEXT_URL
    return context


def model_data_as_dict(data: bytes) -> dict[str, Any]:
    """Interpret a SQLAlchemy JSONB column value as the dict it really is.

    SQLAlchemy's type stubs declare JSONB columns as ``Mapped[bytes]``, but the
    PostgreSQL driver actually deserialises them into Python dicts (or lists).
    This is the **only** place in the codebase that needs ``cast``/``Any`` for
    this conversion; every other module calls this helper instead.
    """
    return cast(dict[str, Any], data)


def load_jsonld_from_model(data: bytes) -> Graph:
    """Load a SQLAlchemy JSONB column value into an rdflib Graph."""
    return load_jsonld(model_data_as_dict(data))


def normalize_context(data: object) -> object:
    """Replace a reference to the Bluecore context document with bibframe-json's.

    Resources we serialize advertise their context by URL
    ('<bluecore>/api/context.jsonld'), so a client that round-trips one back to
    us -- GET a Work, edit it, PUT it -- sends that URL. That document is the
    bibframe-json context, which bluecore_models resolves out of the installed
    package when it is named by its own URL, and refuses to fetch otherwise. So
    substitute the bibframe-json URL here.
    """
    if isinstance(data, list):
        return [normalize_context(node) for node in data]
    if isinstance(data, dict) and "@context" in data:
        return {**data, "@context": _normalize(data["@context"])}
    return data


def with_context(data: object) -> None:
    """Name a context on a stored resource we are about to serve, if it has none.

    A resource the reframe DAG in bluecore-workflows has framed already names
    the bibframe-json context it was framed with, and that is the one to serve:
    it says which terms the document was actually written in. Only data stored
    before then, which carries no @context, is given ours. Mutates the data in
    place, as the callers serve it straight from the model.
    """
    if isinstance(data, dict):
        data.setdefault("@context", CONTEXT_URL)


def check_context(data: object) -> None:
    """Raise ValueError unless every node's @context is one bluecore_models reads.

    That is no @context, or the bibframe-json context URL. An inline context is
    refused, since it can reference a remote one; see terms_for.
    """
    for node in data if isinstance(data, list) else [data]:
        if isinstance(node, dict):
            terms_for(node)
