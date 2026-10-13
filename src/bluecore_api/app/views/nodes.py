"""The bottom layer of the views: turning values into words and links.

`value_text` and `value_href` name and link any value a model holds, a
literal or a reference, wherever nothing more particular reads it. The rest
are small helpers over uris and the display dicts the templates read:
`value` makes one, `dedupe` drops repeats, `link_uri` decides what is worth
linking to. `referenced_uris` is the one helper that still walks a stored
record's raw JSON, because collecting every uri it mentions is a job over the
whole graph rather than a reading of named properties.

It knows nothing about fields, sidebars or vocabularies.
"""

import re
from collections.abc import Iterable
from urllib.parse import urlparse

from bluecore_models.utils.graph import CONTEXT

from bluecore_api.constants import BLUECORE_URL
from bluecore_api.schemas import bibframe

# The only host whose readable page url we know how to build.
LC_ID_HOST = "id.loc.gov"


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


def value(text: str, href: str | None = None) -> dict[str, object]:
    """One line for the page: its text, and a link if it has somewhere to go.

    Every rendered value passes through here, so the templates can count on the
    shape.
    """
    return {"text": text, "href": href, "internal": _is_bluecore(href)}


def referenced_uris(node: object, found: set[str]) -> None:
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


# The context's prefixes, so a compacted id can be linked to. Framing compacts
# an @id against them, which turns ".../bibframe/relatedTo" into "bf:relatedTo".
_PREFIXES = {
    prefix: namespace
    for prefix, namespace in CONTEXT.items()
    if not prefix.startswith("@") and isinstance(namespace, str)
}


def expand_curie(value: str) -> str:
    """The full uri behind a compacted id: "bf:relatedTo" -> ".../relatedTo"."""
    prefix, sep, local = value.partition(":")
    if sep and not local.startswith("//") and prefix in _PREFIXES:
        return _PREFIXES[prefix] + local
    return value


def link_uri(value: object) -> str | None:
    """A uri worth linking to, or None.

    Blank-node ids like "_:b25" are strings but address nothing outside the
    record they came from, so they never become links. A compacted id is
    expanded first, since "bf:relatedTo" is no address either.
    """
    if isinstance(value, str) and not value.startswith("_:"):
        return expand_curie(value)
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


def dedupe(values: list[dict[str, object]]) -> list[dict[str, object]]:
    """Drop values that would render identically, keeping the original order.

    Records often repeat the same title or contribution.
    """
    seen: set[tuple[str, str, str | None]] = set()
    unique: list[dict[str, object]] = []
    for v in values:
        # the prefix counts: "Isbn: 123" and "Lccn: 123" are different lines
        key = (
            str(v.get("prefix", "")),
            str(v["text"]),
            str(v["href"]) if v["href"] else None,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(v)
    return unique


def capitalize(text: str) -> str:
    """Capitalizes the first letter only, leaving the rest as written.

    "series" becomes "Series", but "MARC key" is not flattened to "Marc key".
    """
    return text[:1].upper() + text[1:]


# --- reading the models -------------------------------------------------------


def value_text(value: bibframe.Value) -> str:
    """The text a value shows wherever nothing more particular reads it.

    A literal's own text. A node's label, else its rdf:value, else the label
    of a note it carries, else its code, else the tail of its uri -- the ways
    the values on stage are actually named, in the order they win.
    """
    if isinstance(value, bibframe.Text):
        return str(value)
    if value.states("rdfs:label"):
        return ", ".join(filter(None, map(value_text, value.label)))
    if value.states("rdf:value"):
        return ", ".join(
            filter(None, map(value_text, value.values("rdf:value")))
        ).strip()
    noted = distinct(value_text(note) for note in value.values("note"))
    if noted:
        return noted
    if value.states("code"):
        return ", ".join(filter(None, map(value_text, value.values("code"))))
    return id_tail(value.uri) if value.uri else ""


def distinct(texts: Iterable[str]) -> str:
    """Several texts as one line, each once, in the order they came."""
    return ", ".join(dict.fromkeys(filter(None, texts)))


def value_href(value: bibframe.Value) -> str | None:
    """Where a value links to: its own uri, or the locator it points at.

    Supplementary content has no uri of its own -- only an electronicLocator.
    """
    if isinstance(value, bibframe.Text):
        return None
    own = link_uri(value.uri)
    if own:
        return own
    for locator in value.values("electronicLocator"):
        found = link_uri(
            str(locator) if isinstance(locator, bibframe.Text) else locator.uri
        )
        if found:
            return found
    return None
