"""Builds the main column: a record's properties as labeled fields.

FIELD_ORDER sets position, FIELD_LABELS sets wording, NON_FIELD_KEYS withholds.
"""

from typing import Any

from bluecore_api.app.views import nodes, vocabulary

# The status marking a stubbed-out record. A literal, so rendering never depends
# on a newer bluecore_models release.
STUB_STATUS = "http://id.loc.gov/vocabulary/mstatus/incmp"


def _is_stub_status(value: Any) -> bool:
    """Whether a bf:status value is the one we record on a stub."""
    return any(
        isinstance(item, dict) and item.get("@id") == STUB_STATUS
        for item in nodes.as_list(value)
    )


# A pseudo-key, because bf:title feeds two headings: the title proper and the
# variants, as LC separates them.
VARIANT_TITLE_KEY = "title:variant"

VARIANT_TITLE_LABEL = "Other Titles (e.g. Variant)"

# The two headings bf:title feeds, so Type can be inserted after both of them.
TITLE_LABELS = frozenset({"Title", VARIANT_TITLE_LABEL})

# The order fields appear in, following LC's; one sequence for all three record
# types, since a record skips the keys it does not carry. It does NOT decide what
# renders -- a key missing from here still gets a section, just at the end.
FIELD_ORDER: tuple[str, ...] = (
    "title",
    VARIANT_TITLE_KEY,
    # Type is inserted after the titles by _insert_type_field
    "contribution",
    "subject",
    "genreForm",
    "language",
    "illustrativeContent",
    "classification",
    "electronicLocator",
    "identifiedBy",
    "colorContent",
    "notation",
    "content",
    "bflc:serialPubType",
    "note",
    "supplementaryContent",
    "summary",
    "tableOfContents",
    "dimensions",
    "extent",
    "provisionActivity",
    "publicationStatement",
    "responsibilityStatement",
    "media",
    "issuance",
    "carrier",
    "systemRequirement",
    "frequency",
    "originDate",
    "originPlace",
    "bflc:aap",
)

# The only keys that never become a field. Everything else a record carries gets
# a section whether FIELD_ORDER names it or not.
NON_FIELD_KEYS = frozenset(
    {
        # structural JSON-LD; @type feeds the Type field
        "@context",
        "@id",
        "@type",
        # rendered as their own blocks after the fields, never as one
        "adminMetadata",
        # the sidebar's links, not fields
        "expressionOf",
        "hasExpression",
        "hasInstance",
        "instanceOf",
        "relation",
        "seriesStatement",
        # a normalization of bflc:aap for matching, never for reading
        "bflc:aap-normalized",
        # raw MARC for data already shown above it; LC omits it too. Move it to
        # FIELD_LABELS to surface it.
        "bflc:marcKey",
    }
)

# Fields never dashed, whatever they hold.
# (all other fields not in list  are bulleted if more than one item in field)
UNBULLETED_LABELS = frozenset(
    {"Admin Metadata", "Alternative Formats", "Blue Core Editors"}
)

# Headings for keys that humanize oddly or that LC words differently.
FIELD_LABELS: dict[str, str] = {
    VARIANT_TITLE_KEY: VARIANT_TITLE_LABEL,
    "bflc:aap": "Authorized Access Point",
    "bflc:marcKey": "MARC Key",
    "genreForm": "Genre Form",
    "geographicCoverage": "Geographic Coverage",
    "illustrativeContent": "Illustrative Content",
    "originDate": "Origin Date(s)",
    "originPlace": "Place of Origin",
    "provisionActivity": "Provision Activity",
    "publicationStatement": "Publication Statement",
    "responsibilityStatement": "Responsibility Statement",
    "tableOfContents": "Table of Contents",
}


def node_values(node: Any, label_map: dict[str, str]) -> list[dict[str, Any]]:
    """Generic rendering of a field's value(s) into display dicts."""
    values: list[dict[str, Any]] = []
    for item in nodes.as_list(node):
        href = nodes.node_href(item)
        text = vocabulary.resolve_label(href, nodes.label_text(item), label_map)
        values.append(nodes.value(text or (href or ""), href))
    return values


# An ISSN record at issn.org is addressed by the number itself, which is the only
# handle we have -- the identifier node carries no uri of its own.
ISSN_TYPES = frozenset({"Issn", "IssnL"})
ISSN_URL = "https://issn.org/resource/issn/{}"


def _identifier_url(bf_type: str, ident: str) -> str | None:
    """The registry page for an identifier, where we know how to address one."""
    if bf_type in ISSN_TYPES and ident:
        return ISSN_URL.format(ident)
    return None


def _identifier_values(node: Any, label_map: dict[str, str]) -> list[dict[str, Any]]:
    """An identifier written as "Issn: 1435-5655", led by the kind of number.

    The number is the link text where a registry page exists, so the kind stays
    outside the link; a qualifier or status trails it, since that is what tells
    two identical-looking numbers apart.
    """
    values: list[dict[str, Any]] = []
    for item in nodes.as_list(node):
        if not isinstance(item, dict):
            continue
        bf_type = item.get("@type", "")
        if isinstance(bf_type, list):
            bf_type = bf_type[0] if bf_type else ""
        bf_type = nodes.id_tail(bf_type) if bf_type else ""
        ident = nodes.scalar(nodes.rdf_value(item) or "").strip()

        href = _identifier_url(bf_type, ident)
        value = nodes.value(ident, href)
        if bf_type:
            value["prefix"] = f"{bf_type}: "
        if href:
            value["external"] = True

        qualifier = nodes.scalar(item.get("qualifier", "")).strip()
        status = item.get("status")
        status_href = (
            nodes.link_uri(status.get("@id")) if isinstance(status, dict) else None
        )
        status_text = vocabulary.resolve_label(
            status_href, nodes.label_text(status) if status else "", label_map
        )
        # both read as one aside: "(paperback, canceled or invalid)"
        extras = [e for e in (qualifier, status_text) if e]
        if extras:
            value["suffixes"] = [{"text": ", ".join(extras)}]
        values.append(value)
    return values


def _contribution_values(node: Any, label_map: dict[str, str]) -> list[dict[str, Any]]:
    """Each Contribution renders as its agent, optionally with the role.

    The Contribution node has no label of its own; the names are in the nested
    "agent" and "role" nodes.
    """
    values: list[dict[str, Any]] = []
    for item in nodes.as_list(node):
        if not isinstance(item, dict):
            values.append(nodes.value(nodes.label_text(item)))
            continue
        agent = item.get("agent")
        agent_href = (
            nodes.link_uri(agent.get("@id")) if isinstance(agent, dict) else None
        )
        agent_text = vocabulary.resolve_label(
            agent_href, nodes.label_text(agent) if agent else "", label_map
        )
        role = item.get("role")
        role_href = nodes.link_uri(role.get("@id")) if isinstance(role, dict) else None
        role_text = vocabulary.resolve_label(
            role_href, nodes.label_text(role) if role else "", label_map
        )
        role_text = vocabulary.RELATOR_LABEL_FALLBACKS.get(role_text, role_text)

        value = nodes.value(agent_text or (agent_href or ""), agent_href)
        # the role is its own vocabulary term, so it links separately from the
        # agent rather than sitting inside the agent's link
        if role_text:
            value["suffixes"] = [{"text": role_text, "href": role_href}]
        values.append(value)
    return values


def _classification_kind(local_name: str) -> str:
    """The short form LC prints for a classification class: "ClassificationLcc"
    -> "LCC". Anything not starting with "Classification" is left alone."""
    tail = local_name.removeprefix("Classification")
    return tail.upper() if tail and tail != local_name else local_name


def _classification_extras(
    item: dict[str, Any], label_map: dict[str, str]
) -> list[dict[str, Any]]:
    """The assigner and status LC prints after a call number, each linked.

    The assigner shows its code ("dlc") the way LC does, rather than the
    organization's full name; the status shows its vocabulary label.
    """
    extras: list[dict[str, Any]] = []
    for label, key in (("Assigner", "assigner"), ("Status", "status")):
        node = item.get(key)
        href = nodes.link_uri(node.get("@id")) if isinstance(node, dict) else None
        if key == "assigner":
            text = nodes.id_tail(href) if href else nodes.label_text(node)
        else:
            text = vocabulary.resolve_label(
                href, nodes.label_text(node) if node else "", label_map
            )
        if text:
            extras.append({"label": label, "text": text, "href": href})
    return extras


def _classification_values(
    node: Any, label_map: dict[str, str]
) -> list[dict[str, Any]]:
    """A call number written the way LC writes it.

    "LCC: ML31 .C595 (Assigner: dlc) (Status: used by assigner)" -- the kind,
    the number itself, then whoever assigned it and how far it is trusted.
    """
    values: list[dict[str, Any]] = []
    for item in nodes.as_list(node):
        if not isinstance(item, dict):
            values.append(nodes.value(nodes.label_text(item)))
            continue
        kinds = [
            t
            for t in nodes.as_list(item.get("@type"))
            if nodes.id_tail(t) != "Classification"
        ]
        kind = _classification_kind(nodes.id_tail(kinds[0])) if kinds else ""
        portion = " ".join(
            p
            for p in (
                nodes.scalar(item.get("classificationPortion", "")),
                nodes.scalar(item.get("itemPortion", "")),
            )
            if p
        )
        text = f"{kind}: {portion}".strip(": ").strip() if kind else portion
        value = nodes.value(text)
        extras = _classification_extras(item, label_map)
        if extras:
            value["suffixes"] = extras
        values.append(value)
    return values


def _provision_values(node: Any, label_map: dict[str, str]) -> list[dict[str, Any]]:
    """A provision activity written as "Publication: New York 1991".

    Led by its kind, then whichever of place, date and statement it carries.
    """
    values: list[dict[str, Any]] = []
    for item in nodes.as_list(node):
        if not isinstance(item, dict):
            values.append(nodes.value(nodes.label_text(item)))
            continue
        types = [
            t for t in nodes.as_list(item.get("@type")) if "ProvisionActivity" not in t
        ]
        kind = nodes.id_tail(types[0]) if types else "Provision"
        place = item.get("place")
        place_href = (
            nodes.link_uri(place.get("@id")) if isinstance(place, dict) else None
        )
        parts = [
            vocabulary.resolve_label(
                place_href, nodes.label_text(place) if place else "", label_map
            ),
            nodes.scalar(item.get("date", "")),
            nodes.scalar(item.get("bflc:simpleStatement", "")),
        ]
        text = f"{kind}: " + " ".join(p for p in parts if p)
        values.append(nodes.value(text.strip(), place_href))
    return values


def _derived_from_values(key: str, node: Any) -> list[dict[str, Any]]:
    """Link a derivedFrom to its source record instead of showing a bare number.

    The label stays outside the link, so the line reads as a label plus a link.
    """
    values: list[dict[str, Any]] = []
    for item in nodes.as_list(node):
        href = item.get("@id") if isinstance(item, dict) else item
        if not isinstance(href, str) or not href.startswith("http"):
            values.append(
                nodes.value(f"{nodes.humanize(key)}: {nodes.label_text(item)}")
            )
            continue
        value = nodes.value(nodes.id_tail(href), nodes.source_record_url(href))
        value["prefix"] = f"{nodes.humanize(key)}: "
        value["external"] = True
        values.append(value)
    return values


def _note_values(node: Any, label_map: dict[str, str]) -> list[dict[str, Any]]:
    """A note led by its kind: "description source: Created from auth.".

    The kind is a second @type beside bf:Note, and it is what tells otherwise
    similar notes apart.
    """
    values: list[dict[str, Any]] = []
    for item in nodes.as_list(node):
        if not isinstance(item, dict):
            values.append(nodes.value(nodes.label_text(item)))
            continue
        text = nodes.label_text(item)
        kinds = [
            t for t in nodes.as_list(item.get("@type")) if nodes.id_tail(t) != "Note"
        ]
        kind = ""
        if kinds:
            kind = label_map.get(kinds[0]) or vocabulary.NOTE_TYPE_LABELS.get(
                nodes.id_tail(kinds[0]), ""
            )
        values.append(nodes.value(f"{kind}: {text}" if kind and text else text))
    return values


def _admin_metadata_fields(node: Any) -> list[dict[str, Any]]:
    """Each AdminMetadata block becomes its own 'Admin Metadata' field.

    Sub-properties show as-is, raw MARC included, pending the metadata group.
    """
    fields: list[dict[str, Any]] = []
    for block in nodes.as_list(node):
        if not isinstance(block, dict):
            continue
        values: list[dict[str, Any]] = []
        for key, val in block.items():
            if key in ("@id", "@type"):
                continue
            if key == "derivedFrom":
                values.extend(_derived_from_values(key, val))
                continue
            value = nodes.value(f"{nodes.humanize(key)}: {nodes.label_text(val)}")
            # flag the stub status here too, not just beside the heading
            if key == "status" and _is_stub_status(val):
                value["alert"] = True
            values.append(value)
        if values:
            fields.append({"label": "Admin Metadata", "values": values})
    return fields


# Fields whose values name a controlled term, so each one is tagged with the
# authority it came from -- see _authority_values.
AUTHORITY_KEYS = {"subject", "genreForm"}

# The authorities whose tag cannot be read off the uri, because it is an agreed
# abbreviation rather than the last path segment ("/authorities/subjects" is
# printed LCSH, not SUBJECTS). Those have to be spelled out, so this table is
# necessarily partial.
#
# Matched as substrings, against the term's bf:source first and then the uri the
# term itself lives at, since a term addressed straight at an authority usually
# carries no bf:source of its own.
AUTHORITY_URI_TAGS: tuple[tuple[str, str], ...] = (
    # LC, whose authorities do not follow the scheme-uri pattern above.
    # childrensSubjects precedes subjects only for readability; the capital S in
    # "childrensSubjects" already keeps the two from colliding.
    ("/authorities/childrensSubjects", "LCSHAC"),
    ("/authorities/subjects", "LCSH"),
    ("/authorities/genreForms", "LCGFT"),
    ("/authorities/names", "LCNAF"),
    ("/authorities/demographicTerms", "LCDGT"),
    ("/authorities/performanceMediums", "LCMPT"),
    # A real-world object is the twin of a name authority record, and LC prints
    # it under the same tag.
    ("/rwo/agents", "LCNAF"),
    # Non-LC registries, whose tags are likewise conventional.
    ("worldcat.org/fast/", "FAST"),
    ("viaf.org/", "VIAF"),
    ("d-nb.info/gnd/", "GND"),
    ("wikidata.org/", "WIKIDATA"),
    ("isni.org/", "ISNI"),
)


def _scheme_tag(item: Any, href: str | None) -> str:
    """The authority a term belongs to, as LC prints it: LCSH, GND, FAST.

    An LC scheme uri names its own tag, so that family needs no listing. Anything
    else is looked up in AUTHORITY_URI_TAGS, by bf:source first and then by the
    term's own uri.

    An authority in neither is tagged with nothing, and the term renders with its
    label and link intact -- only the parenthesised marker is missing.
    """
    source = item.get("source") if isinstance(item, dict) else None
    source_id = source.get("@id") if isinstance(source, dict) else None
    if source_id and "Schemes/" in source_id:
        return nodes.id_tail(source_id).upper()
    for uri in (source_id, href):
        for fragment, tag in AUTHORITY_URI_TAGS:
            if uri and fragment in uri:
                return tag
    return ""


def _authority_values(node: Any, label_map: dict[str, str]) -> list[dict[str, Any]]:
    """A controlled term with the authority it came from: "Periodicals (LCGFT)".

    The tag sits outside the link, and it is what separates the several
    same-named headings a record can carry from different vocabularies.
    """
    values: list[dict[str, Any]] = []
    for item in nodes.as_list(node):
        href = nodes.node_href(item)
        text = vocabulary.resolve_label(href, nodes.label_text(item), label_map)
        value = nodes.value(text or (href or ""), href)
        tag = _scheme_tag(item, href)
        if tag:
            value["suffixes"] = [{"text": tag}]
        values.append(value)
    return values


def _field(
    label: str, key: str, data: dict[str, Any], label_map: dict[str, str]
) -> dict[str, Any] | None:
    """Builds one field -- a heading and its values -- or None if it is empty.

    Most keys render generically; the few with a shape of their own, like
    identifiers and notes, have a dedicated builder.
    """
    if key == VARIANT_TITLE_KEY:
        values = node_values(nodes.split_titles(data.get("title"))[1], label_map)
        return {"label": label, "values": nodes.dedupe(values)} if values else None
    if key not in data:
        return None
    if key == "title":
        # variants get their own heading, so keep them out of Title
        values = node_values(nodes.split_titles(data[key])[0], label_map)
    elif key == "identifiedBy":
        values = _identifier_values(data[key], label_map)
    elif key == "contribution":
        values = _contribution_values(data[key], label_map)
    elif key == "classification":
        values = _classification_values(data[key], label_map)
    elif key == "provisionActivity":
        values = _provision_values(data[key], label_map)
    elif key == "note":
        values = _note_values(data[key], label_map)
    elif key in AUTHORITY_KEYS:
        values = _authority_values(data[key], label_map)
    else:
        values = node_values(data[key], label_map)
    # A node with neither text nor a uri would render as a blank line.
    values = nodes.dedupe([v for v in values if v["text"] or v["href"]])

    return {"label": label, "values": values} if values else None


def _field_label(key: str) -> str:
    """The heading a key gets: its curated label, or the key itself humanized."""
    return FIELD_LABELS.get(key, nodes.humanize(key))


def build_fields(
    data: dict[str, Any],
    label_map: dict[str, str],
    field_order: tuple[str, ...] = FIELD_ORDER,
) -> list[dict[str, Any]]:
    """The fields FIELD_ORDER names, in that order, then whatever else the record has.

    FIELD_ORDER is not a filter: dropping a key from it moves that field to the
    end, not off the page. Only NON_FIELD_KEYS withholds anything.
    """
    fields: list[dict[str, Any]] = []
    for key in field_order:
        built = _field(_field_label(key), key, data, label_map)
        if built:
            fields.append(built)

    extra = sorted(
        key for key in data if key not in field_order and key not in NON_FIELD_KEYS
    )
    for key in extra:
        built = _field(_field_label(key), key, data, label_map)
        if built:
            fields.append(built)

    fields.extend(_admin_metadata_fields(data.get("adminMetadata")))
    return fields


def mark_bulleted(fields: list[dict[str, Any]]) -> None:
    """Marks fields holding more than one value, so the template bullets (dashes) them.

    A single value reads as a statement, so LC leaves it plain and so do we.
    """
    for field in fields:
        if field["label"] not in UNBULLETED_LABELS and len(field["values"]) > 1:
            field["bullets"] = True


# Types the page heading already states, so Type lists only what a record adds
# beyond them. LC does show "Hub" under Type, so a Hub only omits bf:Work.
IMPLIED_WORK_TYPES = frozenset({"Work"})
IMPLIED_HUB_TYPES = frozenset({"Work"})


def extra_types(data: dict[str, Any], implied: frozenset[str]) -> list[dict[str, Any]]:
    """The types to list under the Type heading, minus any the caller skips.

    A Work is typed bf:Work, bf:Text and bf:Monograph all at once. The page
    heading already says "BIBFRAME Work", so callers pass implied={"Work"} to
    leave that one out and list only Text and Monograph.
    """
    types = [
        t for t in nodes.as_list(data.get("@type")) if nodes.id_tail(t) not in implied
    ]
    return [nodes.value(nodes.split_camel_case(nodes.id_tail(t))) for t in types]


def insert_type_field(
    fields: list[dict[str, Any]], types: list[dict[str, Any]]
) -> None:
    """Add the Type field to `fields`, just below the last title heading.

    Titles occupy one heading or two ("Title", then "Other Titles" when the
    record has variants), so this scans for the last of them instead of using a
    fixed position -- at a fixed position Type would land between the two.
    """
    if not types:
        return
    after_titles = 0
    for position, field in enumerate(fields):
        if field["label"] in TITLE_LABELS:
            after_titles = position + 1
    fields.insert(after_titles, {"label": "Type", "values": types})


def is_stub(data: dict[str, Any]) -> bool:
    """Whether this record is a placeholder waiting for its own description."""
    return any(
        isinstance(block, dict) and _is_stub_status(block.get("status"))
        for block in nodes.as_list(data.get("adminMetadata"))
    )
