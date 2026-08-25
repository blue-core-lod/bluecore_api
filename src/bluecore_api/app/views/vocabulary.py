"""Turns vocabulary uris into words a cataloger can read.

Records cite terms by uri and drop the label, so it is looked up here -- from
the OtherResources we hold, or from the tables below when we hold nothing.
"""

import logging
from typing import Any

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

    Without it a contributor reads "n79063767" instead of "King, Stephen, 1947-".
    Terms attached to the record are read first, then any others it cites are
    looked up by uri -- ingestion often records no attachment at all.
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
    """The text to show for a value, preferring a real label over a bare uri.

    A node that already carries its own label keeps it; one that is only a
    reference gets whatever the vocabulary says, or its uri tail if we hold
    nothing.
    """
    if href and (not text or text == nodes.id_tail(href)):
        return label_map.get(href, text)
    return text


# The relators build_label_map cannot name, so they are named here instead.
#
# Being ingested is not enough. These two are held as OtherResources like every
# other relator, but the stored document is a bare {"@id", "code", "@type":
# "Role"} carrying no label at all, so there is nothing for build_label_map to
# read and the role would otherwise render as its code. Every other relator in
# use -- 26 of 28 -- arrives with its own rdfs:label and resolves normally, which
# is why they are deliberately absent from this table rather than missing from it.
RELATOR_LABEL_FALLBACKS: dict[str, str] = {
    "ctb": "contributor",
    "pbl": "publisher",
}

# Note kinds, which we never hold as terms at all. An unlisted kind is left off
# rather than guessed at.
NOTE_TYPE_LABELS: dict[str, str] = {
    "datasource": "data source",
    "descsource": "description source",
}


# LC's own spellings, since slugs like "relatedwork" cannot be split reliably;
# _relationship_words guesses at anything unlisted. The order here is LC's
# heading order, which _SECTION_ORDER reads -- so a term the guess would spell
# correctly anyway is still listed, to place its heading rather than to name it.
#
# Keys are the tail of the relationship's @id exactly as written, so the casing
# is the source vocabulary's, not ours. LC's relationship vocabulary is all
# lowercase ("series", "partof"); BIBFRAME ontology properties are camelCase
# ("hasSeries", "relatedTo"). Records cite both, so both spellings are listed.
RELATIONSHIP_LABELS: dict[str, str] = {
    "series": "Series",
    "hasSeries": "Series",
    "seriesof": "Series of",
    "relatedwork": "Related work",
    "musicformotionpicture": "Music for motion picture",
    "partof": "Part of",
    "holdingof": "Holding of",
    "otherphysicalformat": "Other physical format",
    "reproducedas": "Reproduced as",
    "translatedas": "Translated as",
    "onlineversion": "Online version",
    "printversion": "Print version",
    "relatedTo": "Related To",
}

# OCLC records which WorldCat entity a Work corresponds to, and writes it as a
# bf:Relation like any other. It is an identity statement about the record, not a
# link to another record: the target is an opaque entity id carrying no label, so
# the sidebar can only print the id back at the reader. Left out for that reason.
EXTERNAL_RELATIONSHIPS = frozenset(
    {
        "https://id.oclc.org/worldcat/ontology/hasWork",
    }
)


def is_exempt_relation(relation: dict[str, Any]) -> bool:
    """True for a relation asserting an external identity rather than a link."""
    return any(
        term.get("@id") in EXTERNAL_RELATIONSHIPS
        for term in nodes.as_list(relation.get("relationship"))
        if isinstance(term, dict)
    )


# Two slugs can share a heading ("series" and "hasSeries" are both Series), so
# the positions come from the distinct labels -- otherwise the last real heading
# collides with the fallback given to unlisted ones.
_SECTION_ORDER = {
    label: position
    for position, label in enumerate(dict.fromkeys(RELATIONSHIP_LABELS.values()))
}


def section_order(label: str) -> int:
    """Sort key that puts sidebar headings in the order LC shows them.

    Headings we have no order for sort after the ones we do.
    """
    return _SECTION_ORDER.get(label, len(_SECTION_ORDER))


# Words a slug may end in, so an unlisted term still reads as words:
# "precededby" -> "Preceded by".
_RELATIONSHIP_TAILS = ("work", "with", "from", "for", "as", "by", "of", "to")


def _relationship_words(tail: str) -> str:
    """Splits a run-together slug into words: "precededby" -> "Preceded by"."""
    for word in _RELATIONSHIP_TAILS:
        if tail.endswith(word) and len(tail) > len(word):
            return nodes.humanize(f"{tail[: -len(word)]} {word}")
    return nodes.humanize(tail)


# "Print version" and "Online version" already say the thing is another physical
# format, so LC drops the generic term when a relation names both. It keeps both
# where the second term means something else -- work 23209928 shows "Other
# physical format" and "Reproduced as" together.
GENERIC_FORMAT_TERM = "otherphysicalformat"


def _drop_redundant_format(terms: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop the generic format heading when a specific version heading is there."""
    if any(slug.endswith("version") for slug, _ in terms):
        return [(slug, label) for slug, label in terms if slug != GENERIC_FORMAT_TERM]
    return terms


def relationship_labels(
    relation: dict[str, Any], label_map: dict[str, str]
) -> list[str]:
    """Every heading a relation belongs under, one per bf:relationship term.

    A relation routinely names two at once -- "partof" and "holdingof" -- and LC
    lists it under both rather than choosing between them. A term described in
    place instead of referenced supplies its own label.
    """
    terms: list[tuple[str, str]] = []
    for term in nodes.as_list(relation.get("relationship")):
        if not isinstance(term, dict):
            continue
        href = nodes.link_uri(term.get("@id"))
        if href:
            slug = nodes.id_tail(href)
            held = label_map.get(href)
            label = (
                nodes.capitalize(held)
                if held
                else RELATIONSHIP_LABELS.get(slug) or _relationship_words(slug)
            )
            terms.append((slug, label))
            continue
        text = nodes.label_text(term)
        if text:
            terms.append(("", nodes.capitalize(text)))
    return [label for _, label in _drop_redundant_format(terms)] or ["Related"]
