"""Normalizing inbound JSON-LD before it is parsed into a graph."""

from typing import Any
from urllib.parse import urlparse

from bluecore_models.utils.graph import CONTEXT

from bluecore_api.constants import CONTEXT_URL

_CONTEXT_PATH = urlparse(CONTEXT_URL).path


def _is_bluecore_context(reference: Any) -> bool:
    """Does this @context entry point at the Bluecore context document?

    Matches the context URL of any Bluecore deployment, not just this one, so
    that data downloaded from production can be sent back to a development
    server (and vice versa).
    """
    return isinstance(reference, str) and (
        reference == CONTEXT_URL or urlparse(reference).path == _CONTEXT_PATH
    )


def _inline(context: Any) -> Any:
    if _is_bluecore_context(context):
        return CONTEXT
    if isinstance(context, list):
        return [CONTEXT if _is_bluecore_context(entry) else entry for entry in context]
    return context


def inline_context(data: Any) -> Any:
    """Replace a reference to the Bluecore context document with the context itself.

    Resources we serialize advertise their context by URL
    ('<bluecore>/api/context.jsonld'), so a client that round-trips one back to
    us -- GET a Work, edit it, PUT it -- sends that URL. Both parsers we hand the
    body to (rdflib for the graph, pyld for framing on persist) resolve a context
    URL over the network, which is a needless request in production and fails
    outright in development, where the URL only resolves outside the container.
    The context document is bundled in bluecore_models, so substitute it here.
    """
    if isinstance(data, list):
        return [inline_context(node) for node in data]
    if isinstance(data, dict) and "@context" in data:
        return {**data, "@context": _inline(data["@context"])}
    return data
