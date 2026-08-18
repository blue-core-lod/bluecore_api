"""Unit tests for serialize/fields.py -- a record's properties as labelled fields.

Exercises the builders directly: _identifier_values so the ISBN/LCCN behaviour is
covered whichever rdf:value key form the stored JSON-LD uses, _admin_metadata_fields
for the derivedFrom links, and _build_fields for the rule that a property no
ordered list names still reaches the page.
"""

from bluecore_api.app.views.fields import (
    FIELD_ORDER,
    NON_FIELD_KEYS,
    VARIANT_TITLE_KEY,
    _admin_metadata_fields,
    _build_fields,
    _field_label,
    _identifier_values,
)
from bluecore_api.app.views.values import _title_of

RDF_VALUE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"

CANCINV = "http://id.loc.gov/vocabulary/mstatus/cancinv"


def _texts(values):
    return [v["text"] for v in values]


def test_identifier_values_prefixed_rdf_value_key():
    """Identifiers using the compacted "rdf:value" key are retrieved."""
    node = [
        {"@type": "Lccn", "rdf:value": "  2021062674"},
        {"@type": "Isbn", "rdf:value": "9781000607260"},
    ]
    assert _texts(_identifier_values(node, {})) == [
        "Lccn: 2021062674",
        "Isbn: 9781000607260",
    ]


def test_identifier_values_expanded_rdf_value_key():
    """Identifiers using the fully-expanded rdf:value URI are retrieved too."""
    node = [
        {"@type": "Lccn", RDF_VALUE_URI: "2021062674"},
        {"@type": "Isbn", RDF_VALUE_URI: "9781000607260"},
    ]
    assert _texts(_identifier_values(node, {})) == [
        "Lccn: 2021062674",
        "Isbn: 9781000607260",
    ]


def test_identifier_values_includes_qualifier():
    node = [{"@type": "Isbn", "qualifier": "epub", "rdf:value": "9781000607260"}]
    assert _texts(_identifier_values(node, {})) == ["Isbn: 9781000607260 (epub)"]


def test_identifier_values_status_falls_back_to_code():
    """Without a label map the status shows its vocabulary code tail."""
    node = [
        {
            "@type": "Isbn",
            "qualifier": "paperback",
            "status": {"@id": CANCINV},
            "rdf:value": "9781032075129",
        }
    ]
    assert _texts(_identifier_values(node, {})) == [
        "Isbn: 9781032075129 (paperback, cancinv)"
    ]


def test_identifier_values_status_resolves_label():
    """A status URI present in the label map renders its human label."""
    node = [
        {
            "@type": "Isbn",
            "qualifier": "paperback",
            "status": {"@id": CANCINV},
            "rdf:value": "9781032075129",
        }
    ]
    label_map = {CANCINV: "cancelled or invalid"}
    assert _texts(_identifier_values(node, label_map)) == [
        "Isbn: 9781032075129 (paperback, cancelled or invalid)"
    ]


def test_identifier_values_single_node_not_wrapped_in_list():
    node = {"@type": "Lccn", "rdf:value": "2021062674"}
    assert _texts(_identifier_values(node, {})) == ["Lccn: 2021062674"]


def test_identifier_values_skips_non_dict_items():
    node = ["not-a-dict", {"@type": "Isbn", "rdf:value": "9781000607260"}]
    assert _texts(_identifier_values(node, {})) == ["Isbn: 9781000607260"]


# --- titles ------------------------------------------------------------------
#
# bf:title carries the title proper and any variants together, told apart only by
# the node's type. They get separate headings, the way LC's own views do.


def _fields(data):
    return {
        field["label"]: [v["text"] for v in field["values"]]
        for field in _build_fields(data, {})
    }


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


def test_variant_titles_get_their_own_heading():
    """The title proper stays under Title; variants move to Other Titles."""
    fields = _fields(VARIANT_AND_PRIMARY)
    assert fields["Title"] == ["1,000 best movies on DVD"]
    assert fields["Other Titles (e.g. Variant)"] == ["One thousand best movies on DVD"]


def test_untyped_title_is_the_title_proper():
    """Nothing marks an untyped node as a variant, so it isn't treated as one."""
    data = {"title": {"mainTitle": "No Type"}}
    assert _fields(data)["Title"] == ["No Type"]
    assert "Other Titles (e.g. Variant)" not in _fields(data)
    assert _title_of(data) == "No Type"


def test_expanded_title_type_uri_is_the_title_proper():
    """The type may arrive as a full URI rather than the compacted term."""
    data = {
        "title": {
            "@type": "http://id.loc.gov/ontologies/bibframe/Title",
            "mainTitle": "Expanded",
        }
    }
    assert _fields(data)["Title"] == ["Expanded"]


def test_a_record_with_only_variant_titles_still_has_a_heading():
    """
    Nothing should disappear: the variant is listed under Other Titles, and the
    resource is still named by it since there is no title proper to prefer.
    """
    data = {"title": [{"@type": "VariantTitle", "mainTitle": "Only Variant"}]}
    fields = _fields(data)
    assert "Title" not in fields
    assert fields["Other Titles (e.g. Variant)"] == ["Only Variant"]
    assert _title_of(data) == "Only Variant"


# --- derivedFrom -------------------------------------------------------------


def _admin_values(block):
    fields = _admin_metadata_fields(block)
    return [v for f in fields for v in f["values"]]


def test_derived_from_links_the_identifier():
    """
    The identifier is the link text and "Derived from" stays outside it, so the
    line reads as a label with a link rather than one long link.
    """
    block = {
        "@type": "AdminMetadata",
        "derivedFrom": {"@id": "http://id.loc.gov/resources/works/23960506"},
    }
    (value,) = _admin_values(block)
    assert value["prefix"] == "Derived from: "
    assert value["text"] == "23960506"
    assert value["href"] == "https://id.loc.gov/resources/works/23960506.html"
    assert value["external"] is True


def test_derived_from_that_is_not_a_uri_stays_plain_text():
    block = {"@type": "AdminMetadata", "derivedFrom": "just a note"}
    (value,) = _admin_values(block)
    assert value["text"] == "Derived from: just a note"
    assert value["href"] is None


def test_other_admin_metadata_keys_are_unchanged():
    """Only derivedFrom becomes a link; the rest still render as Key: value."""
    block = {"@type": "AdminMetadata", "date": "2026-08-13"}
    (value,) = _admin_values(block)
    assert value["text"] == "Date: 2026-08-13"
    assert value["href"] is None


# ---------------------------------------------------------------------------
# FIELD_ORDER sets position, FIELD_LABELS sets wording, and neither is a filter.
# Genre Form, Illustrative Content and Origin Date(s) were each missing from Work
# pages while the order was treated as one.
# ---------------------------------------------------------------------------


def _labels(fields):
    return [f["label"] for f in fields]


def test_a_property_no_list_names_still_gets_a_section():
    """The point of the change: an unnamed property renders rather than vanishing."""
    data = {
        "@id": "https://bluecore.info/works/x",
        "@type": "Work",
        "title": {"@type": "Title", "mainTitle": "A work"},
        "somethingBrandNew": {"rdfs:label": "a value we have never seen"},
    }
    fields = _build_fields(data, {})

    assert "Something brand new" in _labels(fields)
    values = next(f for f in fields if f["label"] == "Something brand new")["values"]
    assert values[0]["text"] == "a value we have never seen"


def test_named_properties_keep_their_place_and_the_rest_follow():
    data = {
        "@id": "https://bluecore.info/works/x",
        "@type": "Work",
        "title": {"@type": "Title", "mainTitle": "A work"},
        "bflc:aap": "Author, A. A work",
        "zzUnknown": {"rdfs:label": "trailing"},
    }
    labels = _labels(_build_fields(data, {}))

    # the ordered list decides Title before the access point ...
    assert labels.index("Title") < labels.index("Authorized Access Point")
    # ... and anything unnamed sorts in after the named ones
    assert labels[-1] == "Zz unknown"


def test_non_field_keys_are_the_only_things_hidden():
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
    labels = _labels(_build_fields(data, {}))

    assert "Genre Form" in labels
    for hidden in ("Bflc:aap-normalized", "MARC Key", "Has instance", "Relation"):
        assert hidden not in labels, hidden


def test_a_field_with_nothing_to_show_is_dropped():
    """A node with neither text nor a uri would render a heading over a blank
    line -- which is how an empty "Supplementary content" reached the page."""
    data = {
        "@id": "https://bluecore.info/works/x",
        "@type": "Work",
        "title": {"@type": "Title", "mainTitle": "A work"},
        "mysteryField": {"@type": "Mystery"},
    }
    labels = _labels(_build_fields(data, {}))

    assert "Mystery field" not in labels


def test_supplementary_content_is_named_by_its_note_and_linked_to_its_locator():
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
    fields = _build_fields(data, {})

    field = next(f for f in fields if f["label"] == "Supplementary content")
    assert field["values"][0]["text"] == "Contributor biographical information"
    assert field["values"][0]["href"] == locator


def test_every_ordered_key_gets_a_readable_heading():
    """FIELD_ORDER holds keys only; the wording comes from FIELD_LABELS or from
    humanising. Neither may produce something like "Aap" or "Variant"."""
    for key in FIELD_ORDER:
        label = _field_label(key)
        assert label, key
        assert label[0].isupper(), (key, label)
        # a key humanised into a fragment of itself needs a curated label
        assert label.lower() not in {"aap", "variant"}, (key, label)


def test_field_label_humanises_anything_uncurated():
    assert _field_label("illustrativeContent") == "Illustrative Content"
    assert _field_label("descriptionConventions") == "Description conventions"
    assert "@id" in NON_FIELD_KEYS


def test_dropping_title_from_the_list_does_not_hide_it():
    """Removing an entry from an ordered list changes where a property renders,
    never whether it renders. title was wrongly in NON_FIELD_KEYS, which made
    commenting ("title", "Title") out hide the title altogether.
    """
    data = {
        "@id": "https://bluecore.info/works/x",
        "@type": "Work",
        "title": [
            {"@type": "Title", "mainTitle": "Wizard and glass"},
            {"@type": "VariantTitle", "mainTitle": "Wizard & glass"},
        ],
    }

    without_title = tuple(k for k in FIELD_ORDER if k != "title")
    fields = _build_fields(data, {}, without_title)
    title = next(f for f in fields if f["label"] == "Title")
    # the title proper, still not mixed in with the variants
    assert [v["text"] for v in title["values"]] == ["Wizard and glass"]
    assert "Other Titles (e.g. Variant)" in _labels(fields)

    # and with neither title entry declared it still reaches the page
    bare = tuple(k for k in FIELD_ORDER if k not in ("title", VARIANT_TITLE_KEY))
    assert "Title" in _labels(_build_fields(data, {}, bare))


def test_declared_title_is_not_rendered_twice():
    """The catch-all skips what the ordered list already read."""
    data = {
        "@id": "https://bluecore.info/works/x",
        "@type": "Work",
        "title": {"@type": "Title", "mainTitle": "Wizard and glass"},
    }

    assert _labels(_build_fields(data, {})).count("Title") == 1


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
            "hasInstance",
            "instanceOf",
            "relation",
            "seriesStatement",
            "bflc:aap-normalized",
            "bflc:marcKey",
        }
    )
