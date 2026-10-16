"""Builds the main column: a record's properties as labeled fields.

FIELD_ORDER sets position, FIELD_LABELS sets wording, NON_FIELD_KEYS withholds.
"""

from bluecore_api.app.views import nodes, vocabulary
from bluecore_api.schemas import bibframe

# The status marking a stubbed-out record. A literal, so rendering never depends
# on a newer bluecore_models release.
STUB_STATUS = "http://id.loc.gov/vocabulary/mstatus/incmp"


# Pseudo-keys, because bf:title feeds three headings: the title proper, the
# subtitle and the variants, as LC separates them.
VARIANT_TITLE_KEY = "title:variant"
SUB_TITLE_KEY = "title:subtitle"

VARIANT_TITLE_LABEL = "Other Titles (e.g. Variant)"
SUB_TITLE_LABEL = "Subtitle"

# The headings bf:title feeds, so Type can be inserted after all of them.
TITLE_LABELS = frozenset({"Title", VARIANT_TITLE_LABEL, SUB_TITLE_LABEL})

# The order fields appear in, following LC's; one sequence for all three record
# types, since a record skips the keys it does not carry. It does NOT decide what
# renders -- a key missing from here still gets a section, just at the end.
FIELD_ORDER: tuple[str, ...] = (
    "title",
    SUB_TITLE_KEY,
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
    SUB_TITLE_KEY: SUB_TITLE_LABEL,
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


def generic_values(
    values: list[bibframe.Value], label_map: dict[str, str]
) -> list[dict[str, object]]:
    """A property with no builder of its own: each value's text, linked where
    it has somewhere to go."""
    built: list[dict[str, object]] = []
    for value in values:
        href = nodes.value_href(value)
        text = vocabulary.resolve_label(href, nodes.value_text(value), label_map)
        built.append(nodes.value(text or (href or ""), href))
    return built


# An ISSN record at issn.org is addressed by the number itself, which is the only
# handle we have -- the identifier node carries no uri of its own.
ISSN_TYPES = frozenset({"Issn", "IssnL"})
ISSN_URL = "https://issn.org/resource/issn/{}"


def _identifier_url(bf_type: str, ident: str) -> str | None:
    """The registry page for an identifier, where we know how to address one."""
    if bf_type in ISSN_TYPES and ident:
        return ISSN_URL.format(ident)
    return None


def joined(texts: list[bibframe.Text]) -> str:
    """Several literals as one line of text, in the order the record holds them."""
    return ", ".join(filter(None, map(str, texts))).strip()


def identifier_values(
    identifiers: list[bibframe.Identifier], label_map: dict[str, str]
) -> list[dict[str, object]]:
    """An identifier written as "Issn: 1435-5655", led by the kind of number.

    The number is the link text where a registry page exists, so the kind stays
    outside the link; a qualifier or status trails it, since that is what tells
    two identical-looking numbers apart.
    """
    values: list[dict[str, object]] = []
    for identifier in identifiers:
        kind = nodes.id_tail(identifier.types[0]) if identifier.types else ""
        number = joined(identifier.value)

        href = _identifier_url(kind, number)
        value = nodes.value(number, href)
        if kind:
            value["prefix"] = f"{kind}: "
        if href:
            value["external"] = True

        qualifier = joined(identifier.qualifier)
        status = identifier.status[0] if identifier.status else None
        status_text, _ = ref_text(status, label_map)
        # both read as one aside: "(paperback, canceled or invalid)"
        extras = [e for e in (qualifier, status_text) if e]
        if extras:
            value["suffixes"] = [{"text": ", ".join(extras)}]
        values.append(value)
    return values


def ref_text(
    ref: bibframe.Ref | None, label_map: dict[str, str]
) -> tuple[str, str | None]:
    """The text and link for a reference: the name it gives itself, else the
    vocabulary's label, else the tail of its uri."""
    if ref is None:
        return "", None
    href = nodes.link_uri(ref.uri)
    return vocabulary.resolve_label(href, nodes.value_text(ref), label_map), href


def _stated(ref: bibframe.Ref, names: tuple[str, ...]) -> str | None:
    """The first of these properties the record fills for `ref`, as one line.

    None when it fills none of them. A property stated but empty is passed
    over: it names nothing, so the next one gets its turn.
    """
    for name in names:
        text = nodes.distinct(map(nodes.value_text, getattr(ref, name)))
        if text:
            return text
    return None


def contribution_values(
    contributions: list[bibframe.Contribution], label_map: dict[str, str]
) -> list[dict[str, object]]:
    """Each Contribution renders as its agent, with its role after it.

    Only the first role shows, though 3% of contributions on stage carry more.
    """
    values: list[dict[str, object]] = []
    for contribution in contributions:
        agent = contribution.agent[0] if contribution.agent else None
        agent_text, agent_href = ref_text(agent, label_map)
        role = contribution.role[0] if contribution.role else None
        role_text, role_href = ref_text(role, label_map)
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


def classification_values(
    classifications: list[bibframe.Classification], label_map: dict[str, str]
) -> list[dict[str, object]]:
    """A call number written the way LC writes it.

    "LCC: ML31 .C595 (Assigner: dlc) (Status: used by assigner)" -- the kind,
    the number itself, then whoever assigned it and how far it is trusted, each
    linked to its vocabulary term. The assigner shows its code ("dlc") the way
    LC does, rather than the organization's full name.
    """
    values: list[dict[str, object]] = []
    for classification in classifications:
        kinds = [
            t for t in classification.types if nodes.id_tail(t) != "Classification"
        ]
        kind = _classification_kind(nodes.id_tail(kinds[0])) if kinds else ""
        portion = " ".join(
            p
            for p in (
                joined(classification.portion),
                joined(classification.item_portion),
            )
            if p
        )
        text = f"{kind}: {portion}".strip(": ").strip() if kind else portion

        extras: list[dict[str, object]] = []
        for assigner in classification.assigner:
            href = nodes.link_uri(assigner.uri)
            code = nodes.id_tail(href) if href else ref_text(assigner, label_map)[0]
            if code:
                extras.append({"label": "Assigner", "text": code, "href": href})
        for status in classification.status:
            status_text, href = ref_text(status, label_map)
            if status_text:
                extras.append({"label": "Status", "text": status_text, "href": href})

        value = nodes.value(text)
        if extras:
            value["suffixes"] = extras
        values.append(value)
    return values


def provision_values(
    activities: list[bibframe.ProvisionActivity], label_map: dict[str, str]
) -> list[dict[str, object]]:
    """A provision activity written as "Publication: New York 1991".

    Led by its kind, then whichever of place, date and statement it carries.
    """
    values: list[dict[str, object]] = []
    for activity in activities:
        kinds = [t for t in activity.types if "ProvisionActivity" not in t]
        kind = nodes.id_tail(kinds[0]) if kinds else "Provision"
        place = activity.place[0] if activity.place else None
        place_text, place_href = ref_text(place, label_map)
        parts = [
            place_text,
            joined(activity.date),
            joined(activity.simple_statement),
        ]
        text = f"{kind}: " + " ".join(p for p in parts if p)
        values.append(nodes.value(text.strip(), place_href))
    return values


def note_values(
    notes: list[bibframe.Value], label_map: dict[str, str]
) -> list[dict[str, object]]:
    """A note led by its kind: "description source: Created from auth.".

    The kind is a second @type beside bf:Note, and it is what tells otherwise
    similar notes apart. A note written as a plain literal has no kind, only
    its text.
    """
    values: list[dict[str, object]] = []
    for note in notes:
        text = nodes.value_text(note)
        if isinstance(note, bibframe.Text):
            values.append(nodes.value(text))
            continue
        kinds = [t for t in note.types if nodes.id_tail(t) != "Note"]
        kind = ""
        if kinds:
            kind = label_map.get(kinds[0]) or vocabulary.NOTE_TYPE_LABELS.get(
                nodes.id_tail(kinds[0]), ""
            )
        values.append(nodes.value(f"{kind}: {text}" if kind and text else text))
    return values


def _derived_from(key: str, values: list[bibframe.Value]) -> list[dict[str, object]]:
    """Link a derivedFrom to its source record instead of showing a bare number.

    The label stays outside the link, so the line reads as a label plus a link.
    """
    built: list[dict[str, object]] = []
    for value in values:
        href = str(value) if isinstance(value, bibframe.Text) else value.uri
        if not href or not href.startswith("http"):
            built.append(
                nodes.value(f"{nodes.humanize(key)}: {nodes.value_text(value)}")
            )
            continue
        line = nodes.value(nodes.id_tail(href), nodes.source_record_url(href))
        line["prefix"] = f"{nodes.humanize(key)}: "
        line["external"] = True
        built.append(line)
    return built


def admin_metadata_fields(blocks: list[bibframe.Ref]) -> list[dict[str, object]]:
    """Each AdminMetadata block becomes its own 'Admin Metadata' field.

    Sub-properties show as-is, raw MARC included, pending the metadata group.
    """
    built: list[dict[str, object]] = []
    for block in blocks:
        values: list[dict[str, object]] = []
        for key, held in block.properties().items():
            if key == "derivedFrom":
                values.extend(_derived_from(key, held))
                continue
            line = nodes.value(
                f"{nodes.humanize(key)}: {nodes.distinct(map(nodes.value_text, held))}"
            )
            # flag the stub status here too, not just beside the heading
            if key == "status" and any(
                isinstance(v, bibframe.Ref) and v.uri == STUB_STATUS for v in held
            ):
                line["alert"] = True
            values.append(line)
        if values:
            built.append({"label": "Admin Metadata", "values": values})
    return built


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


def _scheme_tag(source_id: str | None, href: str | None) -> str:
    """The authority a term belongs to, as LC prints it: LCSH, GND, FAST.

    An LC scheme uri names its own tag, so that family needs no listing. Anything
    else is looked up in AUTHORITY_URI_TAGS, by bf:source first and then by the
    term's own uri.

    An authority in neither is tagged with nothing, and the term renders with its
    label and link intact -- only the parenthesised marker is missing.
    """
    if source_id and "Schemes/" in source_id:
        return nodes.id_tail(source_id).upper()
    for uri in (source_id, href):
        for fragment, tag in AUTHORITY_URI_TAGS:
            if uri and fragment in uri:
                return tag
    return ""


# Where a controlled term states its name, in the order they win.
def authority_values(
    terms: list[bibframe.Term], label_map: dict[str, str]
) -> list[dict[str, object]]:
    """A controlled term with the authority it came from: "Periodicals (LCGFT)".

    The tag sits outside the link, and it is what separates the several
    same-named headings a record can carry from different vocabularies.
    """
    values: list[dict[str, object]] = []
    for term in terms:
        text, href = ref_text(term, label_map)
        value = nodes.value(text or (href or ""), href)
        tag = _scheme_tag(term.source[0].uri if term.source else None, href)
        if tag:
            value["suffixes"] = [{"text": tag}]
        values.append(value)
    return values


def _title_text(title: bibframe.Title) -> str:
    """A title's text, which is its main title: the subtitle has a heading of
    its own. A title with no main title may say what it is in a note."""
    return nodes.value_text(title)


def title_values(titles: list[bibframe.Title]) -> list[dict[str, object]]:
    """Each title as one line, with nowhere to link to."""
    return nodes.dedupe([nodes.value(_title_text(title)) for title in titles])


def subtitle_values(titles: list[bibframe.Title]) -> list[dict[str, object]]:
    """The subtitles of the title proper, in reading order. A variant's
    subtitle belongs with its variant."""
    return nodes.dedupe(
        [
            nodes.value(str(subtitle))
            for title in titles
            if not title.is_variant
            for subtitle in title.subtitle
        ]
    )


def title_of(resource: bibframe.Resource) -> str:
    """The one title that names a record, for the page heading.

    The title proper, else a variant, else the access point, else the record's
    own label or authoritative label, else the tail of its uri.
    """
    proper = [t for t in resource.title if not t.is_variant]
    variants = [t for t in resource.title if t.is_variant]
    for titles in (proper, variants):
        text = ", ".join(dict.fromkeys(filter(None, map(_title_text, titles))))
        if text:
            return text
    named = joined(resource.aap) or _stated(resource, ("label", "authoritative_label"))
    return named or (nodes.id_tail(resource.uri) if resource.uri else "")


def access_point(resource: bibframe.Resource) -> str:
    """The name LC writes a record under: "King, Stephen, 1947-. Dark tower".

    Held in bflc:aap or rdfs:label depending on the source; the title is a
    fallback.
    """
    return joined(resource.aap) or _stated(resource, ("label",)) or title_of(resource)


def _field(
    label: str, key: str, resource: bibframe.Resource, label_map: dict[str, str]
) -> dict[str, object] | None:
    """Builds one field -- a heading and its values -- or None if it is empty.

    Most keys render generically; the few with a shape of their own, like
    identifiers and notes, have a dedicated builder.
    """
    if key == VARIANT_TITLE_KEY:
        values = title_values([t for t in resource.title if t.is_variant])
        return {"label": label, "values": values} if values else None
    if key == SUB_TITLE_KEY:
        values = subtitle_values(resource.title)
        return {"label": label, "values": values} if values else None
    if not resource.states(key):
        return None
    if key == "title":
        # variants get their own heading, so keep them out of Title
        values = title_values([t for t in resource.title if not t.is_variant])
    elif key == "identifiedBy":
        values = identifier_values(resource.identified_by, label_map)
    elif key == "contribution":
        values = contribution_values(resource.contribution, label_map)
    elif key == "classification":
        values = classification_values(resource.classification, label_map)
    elif key == "provisionActivity":
        values = provision_values(resource.provision_activity, label_map)
    elif key == "note":
        values = note_values(resource.note, label_map)
    elif key == "subject":
        values = authority_values(resource.subject, label_map)
    elif key == "genreForm":
        values = authority_values(resource.genre_form, label_map)
    else:
        values = generic_values(resource.values(key), label_map)
    # A node with neither text nor a uri would render as a blank line.
    values = nodes.dedupe([v for v in values if v["text"] or v["href"]])

    return {"label": label, "values": values} if values else None


def _field_label(key: str) -> str:
    """The heading a key gets: its curated label, or the key itself humanized."""
    return FIELD_LABELS.get(key, nodes.humanize(key))


def build_fields(
    resource: bibframe.Resource,
    label_map: dict[str, str],
    field_order: tuple[str, ...] = FIELD_ORDER,
) -> list[dict[str, object]]:
    """The fields FIELD_ORDER names, in that order, then whatever else the record has.

    FIELD_ORDER is not a filter: dropping a key from it moves that field to the
    end, not off the page. Only NON_FIELD_KEYS withholds anything.
    """
    fields: list[dict[str, object]] = []
    for key in field_order:
        built = _field(_field_label(key), key, resource, label_map)
        if built:
            fields.append(built)

    extra = sorted(
        key
        for key in resource.stated
        if key not in field_order and key not in NON_FIELD_KEYS
    )
    for key in extra:
        built = _field(_field_label(key), key, resource, label_map)
        if built:
            fields.append(built)

    fields.extend(admin_metadata_fields(resource.admin_metadata))
    return fields


def mark_bulleted(fields: list[dict[str, object]]) -> None:
    """Marks fields holding more than one value, so the template bullets (dashes) them.

    A single value reads as a statement, so LC leaves it plain and so do we.
    """
    for field in fields:
        values = field["values"]
        if (
            field["label"] not in UNBULLETED_LABELS
            and isinstance(values, list)
            and len(values) > 1
        ):
            field["bullets"] = True


# Types the page heading already states, so Type lists only what a record adds
# beyond them. LC does show "Hub" under Type, so a Hub only omits bf:Work.
IMPLIED_WORK_TYPES = frozenset({"Work"})
IMPLIED_HUB_TYPES = frozenset({"Work"})


def extra_types(
    resource: bibframe.Resource, implied: frozenset[str]
) -> list[dict[str, object]]:
    """The types to list under the Type heading, minus any the caller skips.

    A Work is typed bf:Work, bf:Text and bf:Monograph all at once. The page
    heading already says "BIBFRAME Work", so callers pass implied={"Work"} to
    leave that one out and list only Text and Monograph.
    """
    types = [t for t in resource.types if nodes.id_tail(t) not in implied]
    return [nodes.value(nodes.split_camel_case(nodes.id_tail(t))) for t in types]


def insert_type_field(
    fields: list[dict[str, object]], types: list[dict[str, object]]
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
