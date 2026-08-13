"""Render the human-facing HTML view of a Work or Instance.
An ordered list of labeled fields whose values are rendered generically, with a
few special cases (identifiers, provision activity, admin metadata) that match
the UI/UX mockups. Referenced Blue Core Works/Instances link to their own URL (their `@id`).
"""

import logging
import re
from typing import Any
from urllib.parse import urlparse

from bluecore_models.models import Instance, Work
from bluecore_models.namespaces import MADS
from bluecore_models.utils.graph import load_jsonld
from fastapi import Request, Response
from rdflib import Graph, URIRef
from rdflib.namespace import RDFS

from bluecore_api.app.templating import BLUECORE_URL, templates

logger = logging.getLogger(__name__)

RDF_VALUE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
# The stored JSON-LD may carry rdf:value either fully expanded or in its
# compacted prefixed form (e.g. identifiers from the API context use "rdf:value").
RDF_VALUE_KEYS = (RDF_VALUE, "rdf:value")

# Status bluecore_models records on a resource a record only stubbed out
# ("incomplete"). Kept as a literal rather than imported so the view doesn't need
# a newer bluecore_models release to render.
STUB_STATUS = "http://id.loc.gov/vocabulary/mstatus/incmp"

# Host whose record pages we know how to link to (see _source_record_url).
LC_ID_HOST = "id.loc.gov"


def _is_stub_status(value: Any) -> bool:
    """Whether a bf:status value is the one we record on a stub."""
    return any(
        isinstance(item, dict) and item.get("@id") == STUB_STATUS
        for item in _as_list(value)
    )


def _rdf_value(node: dict[str, Any]) -> Any:
    """Return the rdf:value of a node, whichever key form it uses."""
    for key in RDF_VALUE_KEYS:
        if key in node:
            return node[key]
    return None


# A pseudo-key for the field tables below: bf:title holds both the title proper
# and any variants, and they get separate headings the way LC's own views do, so
# one json-ld key feeds two display fields. Order stays declarative this way.
VARIANT_TITLE_KEY = "title:variant"
VARIANT_TITLE_LABEL = "Other Titles (e.g. Variant)"

# The headings bf:title feeds, so anything inserted after the titles (the Work
# view's Type) can find where they end rather than assuming a position.
TITLE_LABELS = frozenset({"Title", VARIANT_TITLE_LABEL})

# (json-ld key, human label) in display order. Mirrors the mockups.
INSTANCE_FIELDS: list[tuple[str, str]] = [
    ("title", "Title"),
    (VARIANT_TITLE_KEY, VARIANT_TITLE_LABEL),
    ("identifiedBy", "Identified by"),
    ("contribution", "Contribution"),
    ("note", "Note"),
    ("dimensions", "Dimensions"),
    ("extent", "Extent"),
    ("provisionActivity", "Provision Activity"),
    ("publicationStatement", "Publication Statement"),
    ("responsibilityStatement", "Responsibility Statement"),
    ("media", "Media"),
    ("issuance", "Issuance"),
    ("carrier", "Carrier"),
]

WORK_FIELDS: list[tuple[str, str]] = [
    ("title", "Title"),
    (VARIANT_TITLE_KEY, VARIANT_TITLE_LABEL),
    ("contribution", "Contribution"),
    ("subject", "Subject"),
    ("language", "Language"),
    ("classification", "Classification"),
    ("supplementaryContent", "Supplementary content"),
    ("content", "Content"),
    ("summary", "Summary"),
    ("tableOfContents", "Table of Contents"),
    ("bflc:aap", "Authorized Access Point"),
]


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _scalar(value: Any) -> str:
    """Flatten a label-ish value (str, {@value}, or list) to plain text."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(filter(None, (_scalar(v) for v in value)))
    if isinstance(value, dict):
        if "@value" in value:
            return str(value["@value"])
        return _label_text(value)
    return str(value) if value is not None else ""


def _label_text(node: Any) -> str:
    """Best human-readable label for a JSON-LD node."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        # A record can carry the same title or label twice as separate but
        # identical nodes; dict.fromkeys drops the repeats and keeps the order.
        return ", ".join(dict.fromkeys(filter(None, (_label_text(n) for n in node))))
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
            return _scalar(node[key])
    if any(key in node for key in RDF_VALUE_KEYS):
        return _scalar(_rdf_value(node)).strip()
    if "code" in node:
        return _scalar(node["code"])
    if "@value" in node:
        return str(node["@value"])
    if "@id" in node:
        return _id_tail(node["@id"])
    return ""


def _id_tail(uri: str) -> str:
    return uri.rstrip("/").rsplit("/", 1)[-1]


def _is_bluecore(uri: str | None) -> bool:
    if not uri:
        return False
    return uri.startswith(BLUECORE_URL) or "/works/" in uri or "/instances/" in uri


def _value(text: str, href: str | None = None) -> dict[str, Any]:
    return {"text": text, "href": href, "internal": _is_bluecore(href)}


def _build_label_map(resource: Instance | Work) -> dict[str, str]:
    """Map vocabulary URIs to their labels from the resource's OtherResources.

    Bare references like "media": {"@id": ".../mediaTypes/n"} carry no label
    in the resource's own data, but the referenced term (with its rdfs:label /
    authoritativeLabel) is stored as an attached OtherResource. This lets the view
    show "unmediated" instead of the code "n".
    """
    graph = Graph()
    for row in resource.other_resources:
        other = row.other_resource
        try:
            graph += load_jsonld(other.data)
        except Exception:
            logger.exception("Failed to load OtherResource %s", other.uuid)
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


def _resolve_label(href: str | None, text: str, label_map: dict[str, str]) -> str:
    """Prefer a vocabulary label when the node itself had no embedded label."""
    if href and (not text or text == _id_tail(href)):
        return label_map.get(href, text)
    return text


def _node_values(node: Any, label_map: dict[str, str]) -> list[dict[str, Any]]:
    """Generic rendering of a field's value(s) into display dicts."""
    values: list[dict[str, Any]] = []
    for item in _as_list(node):
        href = item.get("@id") if isinstance(item, dict) else None
        text = _resolve_label(href, _label_text(item), label_map)
        values.append(_value(text or (href or ""), href))
    return values


def _identifier_values(node: Any, label_map: dict[str, str]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in _as_list(node):
        if not isinstance(item, dict):
            continue
        bf_type = item.get("@type", "")
        if isinstance(bf_type, list):
            bf_type = bf_type[0] if bf_type else ""
        ident = _scalar(_rdf_value(item) or "").strip()
        text = f"{bf_type}: {ident}".strip()
        # Qualifier (e.g. "epub") and status (e.g. cancelled/invalid) tell apart
        # otherwise identical-looking numbers, so show them alongside the value.
        qualifier = _scalar(item.get("qualifier", "")).strip()
        status = item.get("status")
        status_href = status.get("@id") if isinstance(status, dict) else None
        status_text = _resolve_label(
            status_href, _label_text(status) if status else "", label_map
        )
        extras = [e for e in (qualifier, status_text) if e]
        if extras:
            text = f"{text} ({', '.join(extras)})"
        values.append(_value(text))
    return values


def _contribution_values(node: Any, label_map: dict[str, str]) -> list[dict[str, Any]]:
    """Each Contribution renders as its agent, optionally with the role.
    The contribution node itself carries no label — the data is in the nested
    "agent" and "role" nodes.
    """
    values: list[dict[str, Any]] = []
    for item in _as_list(node):
        if not isinstance(item, dict):
            values.append(_value(_label_text(item)))
            continue
        agent = item.get("agent")
        agent_href = agent.get("@id") if isinstance(agent, dict) else None
        agent_text = _resolve_label(
            agent_href, _label_text(agent) if agent else "", label_map
        )
        role = item.get("role")
        role_href = role.get("@id") if isinstance(role, dict) else None
        role_text = _resolve_label(
            role_href, _label_text(role) if role else "", label_map
        )
        text = f"{agent_text} ({role_text})" if role_text else agent_text
        values.append(_value(text or (agent_href or ""), agent_href))
    return values


def _classification_values(node: Any) -> list[dict[str, Any]]:
    """Each Classification renders as its call number, optionally prefixed by kind.
    The value lives in "classificationPortion" (+ "itemPortion");
    """
    values: list[dict[str, Any]] = []
    for item in _as_list(node):
        if not isinstance(item, dict):
            values.append(_value(_label_text(item)))
            continue
        types = [
            t for t in _as_list(item.get("@type")) if _id_tail(t) != "Classification"
        ]
        kind = _id_tail(types[0]) if types else ""
        portion = " ".join(
            p
            for p in (
                _scalar(item.get("classificationPortion", "")),
                _scalar(item.get("itemPortion", "")),
            )
            if p
        )
        text = f"{kind}: {portion}".strip(": ").strip() if kind else portion
        values.append(_value(text))
    return values


def _provision_values(node: Any, label_map: dict[str, str]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in _as_list(node):
        if not isinstance(item, dict):
            values.append(_value(_label_text(item)))
            continue
        types = [t for t in _as_list(item.get("@type")) if "ProvisionActivity" not in t]
        kind = _id_tail(types[0]) if types else "Provision"
        place = item.get("place")
        place_href = place.get("@id") if isinstance(place, dict) else None
        parts = [
            _resolve_label(place_href, _label_text(place) if place else "", label_map),
            _scalar(item.get("date", "")),
            _scalar(item.get("bflc:simpleStatement", "")),
        ]
        text = f"{kind}: " + " ".join(p for p in parts if p)
        values.append(_value(text.strip(), place_href))
    return values


def _humanize(key: str) -> str:
    """'descriptionConventions' -> 'Description conventions'."""
    name = key.rsplit("/", 1)[-1] if "://" in key else key.split(":")[-1]
    name = re.sub(r"(?<!^)(?=[A-Z])", " ", name)
    return name[:1].upper() + name[1:].lower()


def _source_record_url(uri: str) -> str:
    """
    The human-readable page for a record a resource was derived from.

    id.loc.gov serves its HTML view at the .html suffix, so the bare resource
    URI we store is turned into the page a cataloger can actually read. Anything
    from another source is linked as-is -- we only know this convention for LC.
    """
    parsed = urlparse(uri)
    if parsed.netloc != LC_ID_HOST:
        return uri
    path = parsed.path.rstrip("/")
    if not path or path.endswith(".html"):
        return f"https://{LC_ID_HOST}{path}"
    return f"https://{LC_ID_HOST}{path}.html"


def _derived_from_values(key: str, node: Any) -> list[dict[str, Any]]:
    """
    Link a derivedFrom to its source record rather than showing a bare number.

    The identifier is the link text and the "Derived from" label stays outside
    it, so the line reads as a label with a link rather than one long link.
    """
    values: list[dict[str, Any]] = []
    for item in _as_list(node):
        href = item.get("@id") if isinstance(item, dict) else item
        if not isinstance(href, str) or not href.startswith("http"):
            values.append(_value(f"{_humanize(key)}: {_label_text(item)}"))
            continue
        value = _value(_id_tail(href), _source_record_url(href))
        value["prefix"] = f"{_humanize(key)}: "
        value["external"] = True
        values.append(value)
    return values


def _admin_metadata_fields(node: Any) -> list[dict[str, Any]]:
    """Each AdminMetadata block becomes its own 'Admin Metadata' field.

    All sub-properties are shown as-is, including raw MARC values (marcKey, the
    040 note, lclocal d9xx) — left unconverted for the metadata group to refine.
    """
    fields: list[dict[str, Any]] = []
    for block in _as_list(node):
        if not isinstance(block, dict):
            continue
        values: list[dict[str, Any]] = []
        for key, val in block.items():
            if key in ("@id", "@type"):
                continue
            if key == "derivedFrom":
                values.extend(_derived_from_values(key, val))
                continue
            value = _value(f"{_humanize(key)}: {_label_text(val)}")
            # flag the stub status here too, not just beside the heading
            if key == "status" and _is_stub_status(val):
                value["alert"] = True
            values.append(value)
        if values:
            fields.append({"label": "Admin Metadata", "values": values})
    return fields


def _dedupe(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop values that display identically, preserving order.

    Source records often carry duplicate triples (e.g. the same title or
    contribution repeated). They render to the same (text, href), so collapse
    them for the HTML view rather than showing the same line several times.
    """
    seen: set[tuple[str, str | None]] = set()
    unique: list[dict[str, Any]] = []
    for v in values:
        key = (v["text"], v["href"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(v)
    return unique


def _label_sources(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append a source tag (LC, FAST, …) to each referenced value.

    Subjects draw from several vocabularies; tagging every value by the
    authority it links to keeps the list consistent and distinguishes
    same-named headings ("Vampires (LC)" vs "Vampires (FAST)").
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


# Fields whose values carry their source tag (see _label_sources).
# Add more as we discover more fields we want to add tags to
SOURCE_LABELED_KEYS = {"subject"}


def _split_titles(node: Any) -> tuple[list[Any], list[Any]]:
    """
    Separate the title proper from variants.

    bf:title carries them together, distinguished only by the node's type: the
    title proper is a plain bf:Title, while a variant is a subtype (bf:VariantTitle
    and friends, often alongside a vartitletype term). Nodes with no type at all
    are treated as the title proper -- there is nothing marking them as a variant.
    """
    primary: list[Any] = []
    variant: list[Any] = []
    for item in _as_list(node):
        if isinstance(item, dict):
            types = [_id_tail(t) for t in _as_list(item.get("@type"))]
        else:
            types = []
        (variant if types and "Title" not in types else primary).append(item)
    return primary, variant


def _field(
    label: str, key: str, data: dict[str, Any], label_map: dict[str, str]
) -> dict[str, Any] | None:
    if key == VARIANT_TITLE_KEY:
        values = _node_values(_split_titles(data.get("title"))[1], label_map)
        return {"label": label, "values": _dedupe(values)} if values else None
    if key not in data:
        return None
    if key == "title":
        # variants get their own heading, so keep them out of Title
        values = _node_values(_split_titles(data[key])[0], label_map)
    elif key == "identifiedBy":
        values = _identifier_values(data[key], label_map)
    elif key == "contribution":
        values = _contribution_values(data[key], label_map)
    elif key == "classification":
        values = _classification_values(data[key])
    elif key == "provisionActivity":
        values = _provision_values(data[key], label_map)
    else:
        values = _node_values(data[key], label_map)
    values = _dedupe(values)
    if key in SOURCE_LABELED_KEYS:
        values = _label_sources(values)
    return {"label": label, "values": values} if values else None


def _build_fields(
    data: dict[str, Any],
    field_defs: list[tuple[str, str]],
    label_map: dict[str, str],
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for key, label in field_defs:
        built = _field(label, key, data, label_map)
        if built:
            fields.append(built)
    fields.extend(_admin_metadata_fields(data.get("adminMetadata")))
    return fields


def _title_of(data: dict[str, Any]) -> str:
    # the title proper names the resource; variants would otherwise all get
    # joined into the heading and into links pointing at it
    primary, variant = _split_titles(data.get("title"))
    return (
        _label_text(primary)
        or _label_text(variant)
        or _scalar(data.get("bflc:aap", ""))
        # Other Resources (authorities/agents/subjects) carry no title; fall back
        # to their rdfs:label / authoritative label before the bare URI tail.
        or _label_text(data)
    )


def resource_title(resource: Instance | Work) -> str:
    """Public helper: a display title for a Work/Instance (used by search)."""
    return _title_of(resource.data)


# Maps an OtherResource's RDF @type (local name, prefix/namespace stripped — so
# bf:Person, mads:PersonalName, etc. collapse together) to the search section it
# belongs in. Edit this table to retune the sections. Anything not listed falls
# back to a humanized, pluralized section of its own type, so new kinds still
# get their own heading rather than a catch-all.
_SECTION_BY_TYPE: dict[str, str] = {
    # Name authorities (agents / names)
    "Person": "Name Authorities",
    "PersonalName": "Name Authorities",
    "Family": "Name Authorities",
    "FamilyName": "Name Authorities",
    "Organization": "Name Authorities",
    "CorporateName": "Name Authorities",
    "Jurisdiction": "Name Authorities",
    "Meeting": "Name Authorities",
    "ConferenceName": "Name Authorities",
    "Agent": "Name Authorities",
    "Name": "Name Authorities",
    # Subjects
    "Topic": "Subjects",
    "Temporal": "Subjects",
    "Geographic": "Subjects",
    "Place": "Subjects",
    "ComplexSubject": "Subjects",
    # Genre / form
    "GenreForm": "Genres & Forms",
    # Classifications
    "Classification": "LC Classifications",
    "ClassificationLcc": "LC Classifications",
    "ClassificationDdc": "Classifications",
    # Hubs
    "Hub": "Hubs",
    # Titles
    "Title": "Titles",
    # Controlled vocabularies
    "Language": "Vocabularies",
    "Content": "Vocabularies",
    "Media": "Vocabularies",
    "Carrier": "Vocabularies",
    "Issuance": "Vocabularies",
}

# Section display order; sections not listed here sort after these, alphabetically.
OTHER_SECTION_ORDER: list[str] = [
    "Name Authorities",
    "Subjects",
    "Genres & Forms",
    "LC Classifications",
    "Classifications",
    "Hubs",
    "Titles",
    "Vocabularies",
]


def _type_localname(rdf_type: str) -> str:
    """'http://.../Hub' / 'mads:PersonalName' -> 'Hub' / 'PersonalName'."""
    tail = rdf_type.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    return tail.split(":")[-1]


def _pluralize(word: str) -> str:
    # Already ends in "s" (e.g. "Description conventions") — assume plural and
    # leave it, rather than producing "conventionses".
    if word.endswith("s"):
        return word
    if word.endswith("y") and word[-2:-1].lower() not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


def resource_section(resource: Instance | Work) -> str:
    """Display section for an OtherResource, derived from its RDF @type.

    Used by the search view to group authorities, vocabularies, classifications,
    hubs, etc. into their own headings. See [[_SECTION_BY_TYPE]].
    """
    types = [_type_localname(t) for t in _as_list(resource.data.get("@type"))]
    for local in types:
        if local in _SECTION_BY_TYPE:
            return _SECTION_BY_TYPE[local]
    if types:
        return _pluralize(_humanize(types[0]))
    return "Other Resources"


def _work_types(data: dict[str, Any]) -> list[dict[str, Any]]:
    types = [t for t in _as_list(data.get("@type")) if _id_tail(t) != "Work"]
    return [_value(_id_tail(t)) for t in types]


def _is_stub(data: dict[str, Any]) -> bool:
    """Whether this record is a placeholder waiting for its own description."""
    return any(
        isinstance(block, dict) and _is_stub_status(block.get("status"))
        for block in _as_list(data.get("adminMetadata"))
    )


def render_instance_html(instance: Instance, request: Request) -> Response:
    data = instance.data
    label_map = _build_label_map(instance)
    fields = _build_fields(data, INSTANCE_FIELDS, label_map)

    sidebar: list[dict[str, Any]] = []
    work = instance.work
    if work is not None:
        # _title_of prefers the Work's title and only falls back to its
        # authorized access point, so this reads the same as the Work's own page
        # and as the "Has Instance" links pointing back the other way.
        label = _title_of(work.data)
        sidebar.append({"label": "Instance of", "values": [_value(label, work.uri)]})
    elif "instanceOf" in data:
        sidebar.append(
            {
                "label": "Instance of",
                "values": _node_values(data["instanceOf"], label_map),
            }
        )

    return templates.TemplateResponse(
        request,
        "resource.html",
        {
            "doc_type": "BIBFRAME Instance",
            "title": _title_of(data),
            "fields": fields,
            "sidebar": sidebar,
            "resource_uri": instance.uri,
            "is_work": False,
            "is_stub": _is_stub(data),
        },
    )


def render_work_html(work: Work, request: Request) -> Response:
    data = work.data
    label_map = _build_label_map(work)
    fields = _build_fields(data, WORK_FIELDS, label_map)
    types = _work_types(data)
    if types:
        # after the titles rather than at a fixed index, so Type can't land
        # between Title and the variants that belong directly under it
        after_titles = 0
        for position, field in enumerate(fields):
            if field["label"] in TITLE_LABELS:
                after_titles = position + 1
        fields.insert(after_titles, {"label": "Type", "values": types})

    sidebar: list[dict[str, Any]] = []
    instance_values = [
        _value(_title_of(inst.data), inst.uri) for inst in work.instances
    ]
    if instance_values:
        sidebar.append({"label": "Has Instance", "values": instance_values})
    if "seriesStatement" in data:
        sidebar.append(
            {
                "label": "Series",
                "values": _node_values(data["seriesStatement"], label_map),
            }
        )

    return templates.TemplateResponse(
        request,
        "resource.html",
        {
            "doc_type": "BIBFRAME Work",
            "title": _title_of(data),
            "fields": fields,
            "sidebar": sidebar,
            "resource_uri": work.uri,
            "is_work": True,
            "is_stub": _is_stub(data),
        },
    )
