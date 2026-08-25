"""Pulls readable text out of stored JSON-LD and wraps it for the templates.

A "node" here is one JSON-LD object out of a record's stored data -- the dict
sitting under a property like bf:title or bf:contribution. A node may carry a
literal, an "@id" referring to another resource, or both, and a property may
hold a single node or a list of them. The helpers below take whatever a property
held and hand back text a template can print.

The bottom layer: it knows nothing about fields, sidebars or vocabularies.
"""

import re
from typing import Any
from urllib.parse import urlparse

from bluecore_api.constants import BLUECORE_URL

RDF_VALUE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"

# Stored data uses either the full uri or the short "rdf:value"; check both.
RDF_VALUE_KEYS = (RDF_VALUE, "rdf:value")

# The only host whose readable page url we know how to build.
LC_ID_HOST = "id.loc.gov"


def rdf_value(node: dict[str, Any]) -> Any:
    """The rdf:value of a node, under whichever of the two key spellings it uses."""
    for key in RDF_VALUE_KEYS:
        if key in node:
            return node[key]
    return None


def as_list(value: Any) -> list:
    """Wraps a value in a list unless it already is one, so callers can loop.

    Stored JSON-LD holds one title as a bare node and two as a list, and most
    code here does not care which it got.
    """
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def scalar(value: Any) -> str:
    """Flattens whatever a key holds -- text, a wrapped literal, a list -- to plain text."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(filter(None, (scalar(v) for v in value)))
    if isinstance(value, dict):
        if "@value" in value:
            return str(value["@value"])
        return label_text(value)
    return str(value) if value is not None else ""


def label_text(node: Any) -> str:
    """The best readable label a node offers, trying each place one can hide.

    Titles, labels and codes all name a node in different records, so they are
    tried in turn and the first one found wins.
    """
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        # dict.fromkeys drops repeated labels and keeps the original order.
        return ", ".join(dict.fromkeys(filter(None, (label_text(n) for n in node))))
    if not isinstance(node, dict):
        return str(node) if node is not None else ""
    for key in (
        "mainTitle",
        "rdfs:label",
        "mads:authoritativeLabel",
        "bflc:authoritativeLabel",
        "label",
    ):
        if key in node:
            return scalar(node[key])
    if any(key in node for key in RDF_VALUE_KEYS):
        return scalar(rdf_value(node)).strip()
    # Some nodes have no label and are described by a nested note instead.
    if "note" in node:
        text = label_text(node["note"])
        if text:
            return text
    if "code" in node:
        return scalar(node["code"])
    if "@value" in node:
        return str(node["@value"])
    if "@id" in node:
        return id_tail(node["@id"])
    return ""


def id_tail(uri: str) -> str:
    """The last segment of a uri: ".../vocabulary/relators/ctb" -> "ctb"."""
    return uri.rstrip("/").rsplit("/", 1)[-1]


def _is_bluecore(uri: str | None) -> bool:
    """Whether a uri points at a record of ours rather than off to another site.

    LC-derived records keep their id.loc.gov uris, so the path is checked as
    well as the host.
    """
    if not uri:
        return False
    return uri.startswith(BLUECORE_URL) or any(
        segment in uri for segment in ("/hubs/", "/works/", "/instances/")
    )


def value(text: str, href: str | None = None) -> dict[str, Any]:
    """One line for the page: its text, and a link if it has somewhere to go.

    Every rendered value passes through here, so the templates can count on the
    shape.
    """
    return {"text": text, "href": href, "internal": _is_bluecore(href)}


def referenced_uris(node: Any, found: set[str]) -> None:
    """Collects every uri a record mentions, however deeply nested, into `found`.

    Used to look up the vocabulary terms a record only references.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "@id":
                if isinstance(value, str) and value.startswith("http"):
                    found.add(value)
            else:
                referenced_uris(value, found)
    elif isinstance(node, list):
        for item in node:
            referenced_uris(item, found)


def link_uri(value: Any) -> str | None:
    """A uri worth linking to, or None.

    Blank-node ids like "_:b25" are strings but address nothing outside the
    record they came from, so they never become links.
    """
    if isinstance(value, str) and not value.startswith("_:"):
        return value
    return None


def node_href(item: Any) -> str | None:
    """Where a value should link to: its own uri, or the locator it points at.

    Supplementary content has no uri of its own -- only an electronicLocator.
    """
    if not isinstance(item, dict):
        return None
    own = link_uri(item.get("@id"))
    if own:
        return own
    locator = item.get("electronicLocator")
    for candidate in as_list(locator):
        if isinstance(candidate, dict):
            found = link_uri(candidate.get("@id"))
            if found:
                return found
        found = link_uri(candidate)
        if found:
            return found
    return None


def humanize(key: str) -> str:
    """Turns a json-ld key into a heading: "descriptionConventions" -> "Description conventions"."""
    name = key.rsplit("/", 1)[-1] if "://" in key else key.split(":")[-1]
    name = re.sub(r"(?<!^)(?=[A-Z])", " ", name)
    return name[:1].upper() + name[1:].lower()


def split_camel_case(text: str) -> str:
    """Spaces out a run-together name: "MovingImage" -> "Moving Image".

    Unlike humanize() the existing capitals are kept, and an acronym is left
    whole so "LCCN" does not come out as "L C C N".
    """
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", text)


def source_record_url(uri: str) -> str:
    """LC serves its readable page at the .html suffix, so add it.

    Any other host is returned unchanged; we only know LC's convention.
    """
    parsed = urlparse(uri)
    if parsed.netloc != LC_ID_HOST:
        return uri
    path = parsed.path.rstrip("/")
    if not path or path.endswith(".html"):
        return f"https://{LC_ID_HOST}{path}"
    return f"https://{LC_ID_HOST}{path}.html"


def dedupe(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop values that would render identically, keeping the original order.

    Records often repeat the same title or contribution.
    """
    seen: set[tuple[str, str, str | None]] = set()
    unique: list[dict[str, Any]] = []
    for v in values:
        # the prefix counts: "Isbn: 123" and "Lccn: 123" are different lines
        key = (v.get("prefix", ""), v["text"], v["href"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(v)
    return unique


def split_titles(node: Any) -> tuple[list[Any], list[Any]]:
    """Split bf:title into the title proper and any variants.

    A variant is any subtype of bf:Title; an untyped node counts as the proper one.
    """
    primary: list[Any] = []
    variant: list[Any] = []
    for item in as_list(node):
        if isinstance(item, dict):
            types = [id_tail(t) for t in as_list(item.get("@type"))]
        else:
            types = []
        (variant if types and "Title" not in types else primary).append(item)
    return primary, variant


def title_of(data: dict[str, Any]) -> str:
    """The one title that names a record, for a heading or a link.

    Falls back to the access point, then to any plain label, so authorities and
    agents -- which carry no title at all -- still come back with something.
    """
    # Only the title proper names the resource; variants would all get joined in.
    primary, variant = split_titles(data.get("title"))
    return (
        label_text(primary)
        or label_text(variant)
        or scalar(data.get("bflc:aap", ""))
        # Authorities and agents have no title at all, only a label.
        or label_text(data)
    )


def capitalize(text: str) -> str:
    """Capitalizes the first letter only, leaving the rest as written.

    "series" becomes "Series", but "MARC key" is not flattened to "Marc key".
    """
    return text[:1].upper() + text[1:]


def access_point(data: dict[str, Any]) -> str:
    """The name LC writes a record under: "King, Stephen, 1947-. Dark tower".

    Held in bflc:aap or rdfs:label depending on the source; the title is a fallback.
    """
    for key in ("bflc:aap", "rdfs:label"):
        text = scalar(data.get(key, ""))
        if text:
            return text
    return title_of(data)
