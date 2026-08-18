"""Turns vocabulary uris into words a cataloguer can read.

Records cite terms by uri and drop the label, so it is looked up here -- from
the OtherResources we hold, or from the tables below when we hold nothing.
"""

import logging
from typing import Any
from urllib.parse import urlparse

from bluecore_models.models import Hub, Instance, OtherResource, Work
from bluecore_models.namespaces import MADS
from bluecore_models.utils.graph import load_jsonld
from rdflib import Graph, URIRef
from rdflib.namespace import RDFS
from sqlalchemy.orm import object_session

from bluecore_api.app.views import nodes

logger = logging.getLogger(__name__)


def build_label_map(resource: Hub | Instance | Work) -> dict[str, str]:
    """Maps each uri a record cites to its label, so pages show words not codes.

    Attached OtherResources first, then a lookup by uri -- ingestion often
    records no attachment, and without the lookup the page shows bare ids.
    """
    graph = Graph()
    for row in resource.other_resources:
        other = row.other_resource
        try:
            graph += load_jsonld(other.data)
        except Exception:
            logger.exception("Failed to load OtherResource %s", other.uuid)
            continue

    session = object_session(resource)
    cited: set[str] = set()
    nodes.referenced_uris(resource.data, cited)
    cited.discard(resource.uri)
    if cited and session is not None:
        for other in (
            session.query(OtherResource).where(OtherResource.uri.in_(cited)).all()
        ):
            try:
                graph += load_jsonld(other.data)
            except Exception:
                logger.exception("Failed to load OtherResource %s", other.uri)
                continue
    label_map: dict[str, str] = {}
    for subject in set(graph.subjects()):
        if not isinstance(subject, URIRef):
            continue
        label = graph.value(subject, RDFS.label) or graph.value(
            subject, MADS.authoritativeLabel
        )
        if label is not None:
            label_map[str(subject)] = str(label)
    return label_map


def resolve_label(href: str | None, text: str, label_map: dict[str, str]) -> str:
    """Prefer a vocabulary label when the node itself had no embedded label."""
    if href and (not text or text == nodes.id_tail(href)):
        return label_map.get(href, text)
    return text


# A stored bf:Role usually has only a code, no label, so spell the common ones
# out here. Anything unlisted shows its code.
RELATOR_LABELS: dict[str, str] = {
    "aut": "author",
    "cmp": "composer",
    "ctb": "contributor",
    "edt": "editor",
    "ill": "illustrator",
    "nrt": "narrator",
    "pbl": "publisher",
    "prf": "performer",
    "trl": "translator",
}

# Note kinds, which we never hold as terms at all. An unlisted kind is left off
# rather than guessed at.
NOTE_TYPE_LABELS: dict[str, str] = {
    "datasource": "data source",
    "descsource": "description source",
}


def label_sources(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tag each linked value with the authority it came from.

    Subjects come from several, so this separates "Vampires (LC)" from
    "Vampires (FAST)".
    """
    for v in values:
        href = v["href"]
        if not href:
            continue
        host = urlparse(href).netloc.lower()
        if "loc.gov" in host:
            source = "LC"
        elif "worldcat.org" in host:
            source = "FAST" if "/fast/" in href else "WorldCat"
        else:
            source = host.removeprefix("www.").removeprefix("id.")
        if source:
            v["text"] = f"{v['text']} ({source})"
    return values


# LC's own spellings, since slugs like "relatedwork" cannot be split reliably;
# _relationship_words guesses at anything unlisted. The order here is LC's
# heading order, which _section_order follows.
RELATIONSHIP_LABELS: dict[str, str] = {
    "seriesof": "Series of",
    "onlineversion": "Online version",
    "otherphysicalformat": "Other physical format",
    "relatedwork": "Related work",
    "partof": "Part of",
    "translatedas": "Translated as",
    "relatedTo": "Related To",
}

_SECTION_ORDER = {
    label: position for position, label in enumerate(RELATIONSHIP_LABELS.values())
}


def section_order(label: str) -> int:
    """Sort key putting known relationship headings in LC's display order."""
    return _SECTION_ORDER.get(label, len(_SECTION_ORDER))


# Words a slug may end in, so an unlisted term still reads as words:
# "precededby" -> "Preceded by".
_RELATIONSHIP_TAILS = ("work", "with", "from", "for", "as", "by", "of", "to")


def _relationship_words(tail: str) -> str:
    """Best effort at spacing a run-together relationship slug."""
    for word in _RELATIONSHIP_TAILS:
        if tail.endswith(word) and len(tail) > len(word):
            return nodes.humanize(f"{tail[: -len(word)]} {word}")
    return nodes.humanize(tail)


# One relation can carry several terms, and LC still shows a single heading --
# taking the more specific designator, which lives in this namespace. Inferred
# from one record (work 23867197), so revisit if a counter-example turns up.
SPECIFIC_RELATIONSHIP_NS = "id.loc.gov/entities/relationships/"


def _relationship_term(node: Any) -> str | None:
    """The uri of the one relationship term a heading is taken from."""
    uris = [
        term["@id"]
        for term in nodes.as_list(node)
        if isinstance(term, dict) and isinstance(term.get("@id"), str)
    ]
    if not uris:
        return None
    for uri in uris:
        if SPECIFIC_RELATIONSHIP_NS in uri:
            return uri
    return uris[0]


def relationship_label(relation: dict[str, Any], label_map: dict[str, str]) -> str:
    """The heading a relation sits under, from its bf:relationship term.

    Tries the vocabulary we hold, then RELATIONSHIP_LABELS, then the uri's tail.
    """
    node = relation.get("relationship")
    href = _relationship_term(node)
    if href:
        label = label_map.get(href)
        if label:
            return nodes.capitalize(label)
        tail = nodes.id_tail(href)
        return RELATIONSHIP_LABELS.get(tail) or _relationship_words(tail)
    label = nodes.label_text(node) if node else ""
    return nodes.capitalize(label) if label else "Related"
