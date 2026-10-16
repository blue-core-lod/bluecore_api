"""Unit tests for views/fields.py -- a record's properties as labeled fields.

Exercises the builders directly: identifier_values so the ISBN/LCCN behavior is
covered whichever rdf:value key form the stored JSON-LD uses, _admin_metadata_fields
for the derivedFrom links, and _build_fields for the rule that a property no
ordered list names still reaches the page.
"""

from bluecore_models.models import Hub

from bluecore_api.app.views.fields import (
    FIELD_ORDER,
    IMPLIED_HUB_TYPES,
    NON_FIELD_KEYS,
    VARIANT_TITLE_KEY,
    _field_label,
    admin_metadata_fields,
    build_fields,
    extra_types,
    identifier_values,
    title_of,
)

RDF_VALUE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"

CANCINV = "http://id.loc.gov/vocabulary/mstatus/cancinv"


def _texts(values):
    """Each value as the page shows it: prefix, text, then any qualifiers."""
    lines = []
    for v in values:
        line = f"{v.get('prefix', '')}{v['text']}"
        for s in v.get("suffixes", []):
            label = f"{s['label']}: " if s.get("label") else ""
            line += f" ({label}{s['text']})"
        lines.append(line)
    return lines


def _identifiers(stored, node, label_map=None):
    """The identifier lines for a record holding `node` under identifiedBy."""
    resource = stored(identifiedBy=node)
    return _texts(identifier_values(resource.identified_by, label_map or {}))


def test_identifier_values_prefixed_rdf_value_key(stored):
    """Identifiers using the compacted "rdf:value" key are retrieved."""
    node = [
        {"@type": "Lccn", "rdf:value": "  2021062674"},
        {"@type": "Isbn", "rdf:value": "9781000607260"},
    ]
    assert _identifiers(stored, node) == [
        "Lccn: 2021062674",
        "Isbn: 9781000607260",
    ]


def test_identifier_values_expanded_rdf_value_key(stored):
    """Identifiers using the fully-expanded rdf:value URI are retrieved too."""
    node = [
        {"@type": "Lccn", RDF_VALUE_URI: "2021062674"},
        {"@type": "Isbn", RDF_VALUE_URI: "9781000607260"},
    ]
    assert _identifiers(stored, node) == [
        "Lccn: 2021062674",
        "Isbn: 9781000607260",
    ]


def test_identifier_values_includes_qualifier(stored):
    node = [{"@type": "Isbn", "qualifier": "epub", "rdf:value": "9781000607260"}]
    assert _identifiers(stored, node) == ["Isbn: 9781000607260 (epub)"]


def test_identifier_values_status_falls_back_to_code(stored):
    """Without a label map the status shows its vocabulary code tail."""
    node = [
        {
            "@type": "Isbn",
            "qualifier": "paperback",
            "status": {"@id": CANCINV},
            "rdf:value": "9781032075129",
        }
    ]
    assert _identifiers(stored, node) == ["Isbn: 9781032075129 (paperback, cancinv)"]


def test_identifier_values_status_resolves_label(stored):
    """A status URI present in the label map renders its human label."""
    node = [
        {
            "@type": "Isbn",
            "qualifier": "paperback",
            "status": {"@id": CANCINV},
            "rdf:value": "9781032075129",
        }
    ]
    label_map = {CANCINV: "canceled or invalid"}
    assert _identifiers(stored, node, label_map) == [
        "Isbn: 9781032075129 (paperback, canceled or invalid)"
    ]


def test_identifier_values_single_node_not_wrapped_in_list(stored):
    node = {"@type": "Lccn", "rdf:value": "2021062674"}
    assert _identifiers(stored, node) == ["Lccn: 2021062674"]


def test_an_identifier_that_is_only_a_string_is_dropped(stored):
    """A bare string under identifiedBy reads as a reference to an identifier
    with no number, which has nothing to show."""
    resource = stored(
        identifiedBy=["not-a-dict", {"@type": "Isbn", "rdf:value": "9781000607260"}]
    )
    (field,) = [f for f in build_fields(resource, {}) if f["label"] == "Identified by"]
    assert _texts(field["values"]) == ["Isbn: 9781000607260"]


# --- titles ------------------------------------------------------------------
#
# bf:title carries the title proper and any variants together, told apart only by
# the node's type. They get separate headings, the way LC's own views do.


def _page(stored, data):
    """The fields and heading a record holding `data`'s properties renders."""
    resource = stored(**{k: v for k, v in data.items() if not k.startswith("@")})
    fields: dict[str, list] = {}
    for field in build_fields(resource, {}):
        values = field["values"]
        assert isinstance(values, list)
        fields[str(field["label"])] = [v["text"] for v in values]
    return fields, title_of(resource)


def _fields(stored, data):
    return _page(stored, data)[0]


VARIANT_AND_PRIMARY = {
    "@id": "https://bcld.info/works/7f6c1711-663b-4a7d-a196-21c5a953413c",
    "@type": "Work",
    "title": [
        {
            "@type": ["VariantTitle", "http://id.loc.gov/vocabulary/vartitletype/por"],
            "mainTitle": "One thousand best movies on DVD",
        },
        {"@type": "Title", "mainTitle": "1,000 best movies on DVD"},
    ],
}


def test_variant_titles_get_their_own_heading(stored):
    """The title proper stays under Title; variants move to Other Titles."""
    fields = _fields(stored, VARIANT_AND_PRIMARY)
    assert fields["Title"] == ["1,000 best movies on DVD"]
    assert fields["Other Titles (e.g. Variant)"] == ["One thousand best movies on DVD"]


def test_untyped_title_is_the_title_proper(stored):
    """Nothing marks an untyped node as a variant, so it isn't treated as one."""
    data = {"title": {"mainTitle": "No Type"}}
    assert _fields(stored, data)["Title"] == ["No Type"]
    assert "Other Titles (e.g. Variant)" not in _fields(stored, data)
    assert _page(stored, data)[1] == "No Type"


def test_expanded_title_type_uri_is_the_title_proper(stored):
    """The type may arrive as a full URI rather than the compacted term."""
    data = {
        "title": {
            "@type": "http://id.loc.gov/ontologies/bibframe/Title",
            "mainTitle": "Expanded",
        }
    }
    assert _fields(stored, data)["Title"] == ["Expanded"]


def test_a_record_with_only_variant_titles_still_has_a_heading(stored):
    """
    Nothing should disappear: the variant is listed under Other Titles, and the
    resource is still named by it since there is no title proper to prefer.
    """
    data = {"title": [{"@type": "VariantTitle", "mainTitle": "Only Variant"}]}
    fields = _fields(stored, data)
    assert "Title" not in fields
    assert fields["Other Titles (e.g. Variant)"] == ["Only Variant"]
    assert _page(stored, data)[1] == "Only Variant"


def test_subtitle_gets_its_own_heading(stored):
    """A subtitle is a property of the title node, not a title node of its own."""
    data = {
        "title": {
            "@type": "Title",
            "mainTitle": "Blue light hours",
            "subtitle": "a novel",
        }
    }
    fields = _fields(stored, data)
    assert fields["Title"] == ["Blue light hours"]
    assert fields["Subtitle"] == ["a novel"]


def test_subtitle_arrives_as_a_list(stored):
    """Expanded JSON-LD wraps every literal in a list, subtitles included."""
    data = {
        "title": [
            {
                "@type": ["Title"],
                "mainTitle": ["Blue light hours"],
                "subtitle": ["a novel"],
            }
        ]
    }
    assert _fields(stored, data)["Subtitle"] == ["a novel"]


def test_a_title_without_a_subtitle_has_no_heading(stored):
    assert "Subtitle" not in _fields(stored, VARIANT_AND_PRIMARY)


def test_subtitle_is_not_filled_with_variant_titles(stored):
    """Variants belong under Other Titles; they are not subtitles."""
    data = {
        "title": [
            {"@type": "Title", "mainTitle": "Proper", "subtitle": "a novel"},
            {"@type": "VariantTitle", "mainTitle": "Variant"},
        ]
    }
    fields = _fields(stored, data)
    assert fields["Subtitle"] == ["a novel"]
    assert fields["Other Titles (e.g. Variant)"] == ["Variant"]


def test_a_stub_from_an_authority_is_named_by_its_authoritative_label(stored):
    """190 Works on stage are FAST stubs, with no title of their own."""
    data = {"mads:authoritativeLabel": "Vedas Rgveda Purusasukta"}
    assert _page(stored, data)[1] == "Vedas Rgveda Purusasukta"


def test_a_record_with_nothing_to_name_it_by_is_its_uuid(stored):
    """Not a note, as the dict reader would take: a heading reading "Includes
    bibliographical references." names nothing."""
    data = {
        "title": {"@type": "Title", "subtitle": "a novel"},
        "note": {"@type": "Note", "rdfs:label": "Includes bibliographical references."},
    }
    assert _page(stored, data)[1] == "00000000-0000-4000-8000-000000000000"


def test_a_title_with_no_main_title_can_be_named_by_its_note(stored):
    data = {
        "title": [
            {
                "@type": "VariantTitle",
                "note": {"@type": "Note", "rdfs:label": "English summary title: X"},
            },
            {"@type": "Title", "mainTitle": "Proper"},
        ]
    }
    assert _fields(stored, data)["Other Titles (e.g. Variant)"] == [
        "English summary title: X"
    ]


# --- derivedFrom -------------------------------------------------------------


def _admin_values(stored, block):
    resource = stored(adminMetadata=block)
    values = []
    for field in admin_metadata_fields(resource.admin_metadata):
        held = field["values"]
        assert isinstance(held, list)
        values.extend(held)
    return values


def test_derived_from_links_the_identifier(stored):
    """
    The identifier is the link text and "Derived from" stays outside it, so the
    line reads as a label with a link rather than one long link.
    """
    block = {
        "@type": "AdminMetadata",
        "derivedFrom": {"@id": "http://id.loc.gov/resources/works/23960506"},
    }
    (value,) = _admin_values(stored, block)
    assert value["prefix"] == "Derived from: "
    assert value["text"] == "23960506"
    assert value["href"] == "https://id.loc.gov/resources/works/23960506.html"
    assert value["external"] is True


def test_derived_from_that_is_not_a_uri_stays_plain_text(stored):
    block = {"@type": "AdminMetadata", "derivedFrom": "just a note"}
    (value,) = _admin_values(stored, block)
    assert value["text"] == "Derived from: just a note"
    assert value["href"] is None


def test_other_admin_metadata_keys_are_unchanged(stored):
    """Only derivedFrom becomes a link; the rest still render as Key: value."""
    block = {"@type": "AdminMetadata", "date": "2026-08-13"}
    (value,) = _admin_values(stored, block)
    assert value["text"] == "Date: 2026-08-13"
    assert value["href"] is None


# ---------------------------------------------------------------------------
# FIELD_ORDER sets position, FIELD_LABELS sets wording, and neither is a filter.
# Genre Form, Illustrative Content and Origin Date(s) were each missing from Work
# pages while the order was treated as one.
# ---------------------------------------------------------------------------


def _labels(fields):
    return [f["label"] for f in fields]


def _build(stored, data):
    """The fields a record holding `data` renders, read as a page reads it."""
    resource = stored(**{k: v for k, v in data.items() if k != "@id"})
    return build_fields(resource, {})


def test_a_property_no_list_names_still_gets_a_section(stored):
    """The point of the change: an unnamed property renders rather than vanishing."""
    data = {
        "@id": "https://bluecore.info/works/x",
        "@type": "Work",
        "title": {"@type": "Title", "mainTitle": "A work"},
        "somethingBrandNew": {"rdfs:label": "a value we have never seen"},
    }
    fields = _build(stored, data)

    assert "Something brand new" in _labels(fields)
    values = next(f for f in fields if f["label"] == "Something brand new")["values"]
    assert values[0]["text"] == "a value we have never seen"


def test_named_properties_keep_their_place_and_the_rest_follow(stored):
    data = {
        "@id": "https://bluecore.info/works/x",
        "@type": "Work",
        "title": {"@type": "Title", "mainTitle": "A work"},
        "bflc:aap": "Author, A. A work",
        "zzUnknown": {"rdfs:label": "trailing"},
    }
    labels = _labels(_build(stored, data))

    # the ordered list decides Title before the access point ...
    assert labels.index("Title") < labels.index("Authorized Access Point")
    # ... and anything unnamed sorts in after the named ones
    assert labels[-1] == "Zz unknown"


def test_non_field_keys_are_the_only_things_hidden(stored):
    """Everything a record carries renders unless it is deliberately excluded."""
    data = {
        "@id": "https://bluecore.info/works/x",
        "@type": ["Work", "Text"],
        "title": {"@type": "Title", "mainTitle": "A work"},
        "bflc:aap-normalized": "authorawork",
        "bflc:marcKey": "1001 $aAuthor, A.",
        "hasInstance": {"@id": "https://bluecore.info/instances/y"},
        "relation": {"@type": "Relation"},
        "genreForm": {"rdfs:label": "Fantasy fiction"},
    }
    labels = _labels(_build(stored, data))

    assert "Genre Form" in labels
    for hidden in ("Bflc:aap-normalized", "MARC Key", "Has instance", "Relation"):
        assert hidden not in labels, hidden


def test_a_field_with_nothing_to_show_is_dropped(stored):
    """A node with neither text nor a uri would render a heading over a blank
    line -- which is how an empty "Supplementary content" reached the page."""
    data = {
        "@id": "https://bluecore.info/works/x",
        "@type": "Work",
        "title": {"@type": "Title", "mainTitle": "A work"},
        "mysteryField": {"@type": "Mystery"},
    }
    labels = _labels(_build(stored, data))

    assert "Mystery field" not in labels


def test_supplementary_content_is_named_by_its_note_and_linked_to_its_locator(stored):
    locator = "http://www.loc.gov/catdir/enhancements/fy1209/91032460-b.html"
    data = {
        "@id": "https://bluecore.info/instances/x",
        "@type": "Instance",
        "supplementaryContent": {
            "@type": "SupplementaryContent",
            "note": {
                "@type": "Note",
                "rdfs:label": "Contributor biographical information",
            },
            "electronicLocator": {"@id": locator},
        },
    }
    fields = _build(stored, data)

    field = next(f for f in fields if f["label"] == "Supplementary content")
    assert field["values"][0]["text"] == "Contributor biographical information"
    assert field["values"][0]["href"] == locator


def test_every_ordered_key_gets_a_readable_heading():
    """FIELD_ORDER holds keys only; the wording comes from FIELD_LABELS or from
    humanizing. Neither may produce something like "Aap" or "Variant"."""
    for key in FIELD_ORDER:
        label = _field_label(key)
        assert label, key
        assert label[0].isupper(), (key, label)
        # a key humanized into a fragment of itself needs a curated label
        assert label.lower() not in {"aap", "variant"}, (key, label)


def test_field_label_humanizes_anything_uncurated():
    assert _field_label("illustrativeContent") == "Illustrative Content"
    assert _field_label("descriptionConventions") == "Description conventions"
    assert "@id" in NON_FIELD_KEYS


def test_dropping_title_from_the_list_does_not_hide_it(stored):
    """Removing an entry from an ordered list changes where a property renders,
    never whether it renders. title was wrongly in NON_FIELD_KEYS, which made
    commenting ("title", "Title") out hide the title altogether.
    """
    resource = stored(
        title=[
            {"@type": "Title", "mainTitle": "Wizard and glass"},
            {"@type": "VariantTitle", "mainTitle": "Wizard & glass"},
        ]
    )

    without_title = tuple(k for k in FIELD_ORDER if k != "title")
    fields = build_fields(resource, {}, without_title)
    title = next(f for f in fields if f["label"] == "Title")
    values = title["values"]
    assert isinstance(values, list)
    # the title proper, still not mixed in with the variants
    assert [v["text"] for v in values] == ["Wizard and glass"]
    assert "Other Titles (e.g. Variant)" in _labels(fields)

    # and with neither title entry declared it still reaches the page
    bare = tuple(k for k in FIELD_ORDER if k not in ("title", VARIANT_TITLE_KEY))
    assert "Title" in _labels(build_fields(resource, {}, bare))


def test_declared_title_is_not_rendered_twice(stored):
    """The catch-all skips what the ordered list already read."""
    data = {
        "@id": "https://bluecore.info/works/x",
        "@type": "Work",
        "title": {"@type": "Title", "mainTitle": "Wizard and glass"},
    }

    assert _labels(_build(stored, data)).count("Title") == 1


def test_non_field_keys_hold_only_what_is_shown_elsewhere_or_withheld():
    """The deny-list is the one thing that can hide a property, so it should not
    accumulate entries that are merely handled by an ordered list."""
    assert "title" not in NON_FIELD_KEYS
    assert NON_FIELD_KEYS == frozenset(
        {
            "@context",
            "@id",
            "@type",
            "adminMetadata",
            "expressionOf",
            "hasExpression",
            "hasInstance",
            "instanceOf",
            "relation",
            "seriesStatement",
            "bflc:aap-normalized",
            "bflc:marcKey",
        }
    )


def test_type_values_are_spaced_out(stored):
    """A Hub typed bf:MovingImage should read "Moving Image" under Type."""
    data = {
        "@id": "http://localhost/hubs/h",
        "@type": ["Hub", "MovingImage", "Work"],
        "title": {"@type": "Title", "mainTitle": "A film"},
    }

    resource = stored(of=Hub, **{k: v for k, v in data.items() if k != "@id"})
    types = [v["text"] for v in extra_types(resource, IMPLIED_HUB_TYPES)]

    assert types == ["Hub", "Moving Image"]


# --- classification ----------------------------------------------------------

DLC = "http://id.loc.gov/vocabulary/organizations/dlc"
UBA = "http://id.loc.gov/vocabulary/mstatus/uba"


def _classification(stored, node, label_map=None):
    """The one value a record holding `node` under classification renders."""
    resource = stored(classification=node)
    (field,) = [
        f
        for f in build_fields(resource, label_map or {})
        if f["label"] == "Classification"
    ]
    values = field["values"]
    assert isinstance(values, list)
    (value,) = values
    return value


def test_classification_reads_the_way_lc_writes_it(stored):
    """ "LCC: ML31 .C595 (Assigner: dlc) (Status: used by assigner)" -- the kind
    as a short code, then who assigned it and how far it is trusted."""
    value = _classification(
        stored,
        {
            "@type": "ClassificationLcc",
            "classificationPortion": "ML31",
            "itemPortion": ".C595",
            "assigner": {"@id": DLC},
            "status": {"@id": UBA},
        },
        {UBA: "used by assigner"},
    )

    assert value["text"] == "LCC: ML31 .C595"
    assert value["suffixes"] == [
        {"label": "Assigner", "text": "dlc", "href": DLC},
        {"label": "Status", "text": "used by assigner", "href": UBA},
    ]


def test_classification_without_an_assigner_or_status_has_no_qualifiers(stored):
    value = _classification(
        stored, {"@type": "ClassificationDdc", "classificationPortion": "813/.54"}
    )

    assert value["text"] == "DDC: 813/.54"
    assert "suffixes" not in value


def test_each_status_of_a_classification_is_its_own_qualifier(stored):
    """5% of classifications on stage carry two statuses."""
    value = _classification(
        stored,
        {
            "@type": "ClassificationLcc",
            "classificationPortion": "ML31",
            "status": [{"@id": UBA}, {"@id": CANCINV}],
        },
        {UBA: "used by assigner"},
    )

    assert value["suffixes"] == [
        {"label": "Status", "text": "used by assigner", "href": UBA},
        {"label": "Status", "text": "cancinv", "href": CANCINV},
    ]


# --- provision activity ------------------------------------------------------

NYU = "http://id.loc.gov/vocabulary/countries/nyu"


def _provisions(stored, node, label_map=None):
    resource = stored(provisionActivity=node)
    (field,) = [
        f
        for f in build_fields(resource, label_map or {})
        if f["label"] == "Provision Activity"
    ]
    values = field["values"]
    assert isinstance(values, list)
    return [(v["text"], v["href"]) for v in values]


def test_a_provision_activity_reads_as_its_kind_place_and_date(stored):
    node = {
        "@type": ["ProvisionActivity", "Publication"],
        "place": {"@id": NYU},
        "date": {"@value": "1991", "@type": "http://id.loc.gov/datatypes/edtf"},
    }
    assert _provisions(stored, node, {NYU: "New York (State)"}) == [
        ("Publication: New York (State) 1991", NYU)
    ]


def test_a_place_with_no_label_shows_its_code(stored):
    node = {"@type": ["ProvisionActivity", "Production"], "place": {"@id": NYU}}
    assert _provisions(stored, node) == [("Production: nyu", NYU)]


def test_a_provision_activity_of_no_particular_kind(stored):
    node = {"@type": "ProvisionActivity", "date": "1991"}
    assert _provisions(stored, node) == [("Provision: 1991", None)]


# --- notes -------------------------------------------------------------------

DESCSOURCE = "http://id.loc.gov/vocabulary/mnotetype/descsource"


def _notes(stored, node, label_map=None):
    resource = stored(note=node)
    fields = [
        f for f in build_fields(resource, label_map or {}) if f["label"] == "Note"
    ]
    if not fields:
        return []
    values = fields[0]["values"]
    assert isinstance(values, list)
    return [v["text"] for v in values]


def test_a_note_is_led_by_its_kind(stored):
    node = {"@type": ["Note", DESCSOURCE], "rdfs:label": "Created from auth."}
    assert _notes(stored, node) == ["description source: Created from auth."]


def test_a_note_kind_the_vocabulary_names_wins(stored):
    node = {"@type": ["Note", DESCSOURCE], "rdfs:label": "Created from auth."}
    assert _notes(stored, node, {DESCSOURCE: "Description source"}) == [
        "Description source: Created from auth."
    ]


def test_a_note_of_no_known_kind_is_only_its_text(stored):
    assert _notes(stored, {"@type": "Note", "rdfs:label": "Includes index."}) == [
        "Includes index."
    ]


def test_a_note_with_no_text_is_dropped(stored):
    """8,667 notes on stage state only a language."""
    node = {
        "@type": "Note",
        "language": {"@id": "http://id.loc.gov/vocabulary/languages/eng"},
    }
    assert _notes(stored, node) == []


# --- blank nodes never become links -----------------------------------------


def test_a_blank_node_agent_is_named_but_not_linked(stored):
    """LC's json-ld addresses a described-in-place node as "_:b7". It names
    nothing outside the record, so it reads as text rather than a dead link."""
    resource = stored(
        contribution={
            "@type": "Contribution",
            "agent": {"@id": "_:b7", "rdfs:label": "King, Stephen, 1947-"},
        }
    )

    values = build_fields(resource, {})[0]["values"]
    assert isinstance(values, list)
    (value,) = values

    assert value["text"] == "King, Stephen, 1947-"
    assert value["href"] is None


def test_a_blank_node_classification_assigner_is_not_linked(stored):
    value = _classification(
        stored,
        {
            "@type": "ClassificationLcc",
            "classificationPortion": "ML31",
            "assigner": {"@id": "_:b3", "rdfs:label": "dlc"},
        },
    )

    assert value["suffixes"] == [{"label": "Assigner", "text": "dlc", "href": None}]


# --- authority tags ----------------------------------------------------------


def _tag(item, href=None):
    from bluecore_api.app.views.fields import _scheme_tag

    return _scheme_tag(item.get("source", {}).get("@id"), href)


def test_an_lc_scheme_uri_names_its_own_tag():
    """The whole LC scheme family is read off the uri, not listed: a vocabulary
    we have never seen still tags correctly."""
    assert (
        _tag({"source": {"@id": "http://id.loc.gov/vocabulary/subjectSchemes/gnd"}})
        == "GND"
    )
    assert (
        _tag({"source": {"@id": "http://id.loc.gov/vocabulary/genreFormSchemes/aat"}})
        == "AAT"
    )
    assert (
        _tag({"source": {"@id": "http://id.loc.gov/vocabulary/classSchemes/bisacsh"}})
        == "BISACSH"
    )


def test_authorities_whose_tag_is_an_abbreviation_are_listed():
    """These cannot be read off the uri -- "subjects" is printed LCSH."""
    assert _tag({}, "http://id.loc.gov/authorities/subjects/sh85033827") == "LCSH"
    assert (
        _tag({}, "http://id.loc.gov/authorities/childrensSubjects/sj96005537")
        == "LCSHAC"
    )
    assert _tag({}, "http://id.loc.gov/rwo/agents/nb2008026982") == "LCNAF"
    assert _tag({}, "https://viaf.org/viaf/102333412") == "VIAF"
    assert _tag({}, "https://d-nb.info/gnd/118540238") == "GND"


def test_childrens_subjects_does_not_collide_with_subjects():
    """Substring matching, so the two /authorities/ paths must stay distinct."""
    assert (
        _tag({"source": {"@id": "http://id.loc.gov/authorities/childrensSubjects"}})
        == "LCSHAC"
    )


def test_an_unlisted_authority_is_untagged_rather_than_guessed_at():
    """A tag states which vocabulary a heading came from, so a wrong one is worse
    than none. The term itself still renders."""
    assert (
        _tag(
            {},
            "https://scigraph.springernature.com/ontologies/product-market-codes/1000",
        )
        == ""
    )


def _subject(stored, node, label_map=None):
    resource = stored(subject=node)
    (field,) = [
        f for f in build_fields(resource, label_map or {}) if f["label"] == "Subject"
    ]
    values = field["values"]
    assert isinstance(values, list)
    (value,) = values
    return value


def test_an_untagged_term_keeps_its_label_and_link(stored):
    unknown = "https://scigraph.springernature.com/ontologies/product-market-codes/1000"
    value = _subject(stored, {"@id": unknown, "rdfs:label": "Video games"})

    assert value["text"] == "Video games"
    assert value["href"] == unknown
    assert "suffixes" not in value


def test_a_term_is_named_by_its_label_before_its_authoritative_label(stored):
    value = _subject(
        stored,
        {
            "@type": "Topic",
            "rdfs:label": "Cats",
            "mads:authoritativeLabel": "Cats--Behavior",
        },
    )
    assert value["text"] == "Cats"


def test_a_term_with_only_an_authoritative_label_is_named_by_it(stored):
    """19,533 subjects on stage state no rdfs:label."""
    value = _subject(
        stored, {"@type": "ComplexSubject", "mads:authoritativeLabel": "Cats--Behavior"}
    )
    assert value["text"] == "Cats--Behavior"


def test_a_term_with_only_a_code_is_named_by_it(stored):
    """A subject written as a classification code, as 48,514 on stage are."""
    value = _subject(
        stored,
        {
            "@type": "Topic",
            "code": "FIC009000",
            "source": {"@id": "http://id.loc.gov/vocabulary/subjectSchemes/bisacsh"},
        },
    )
    assert value["text"] == "FIC009000"
    assert value["suffixes"] == [{"text": "BISACSH"}]
