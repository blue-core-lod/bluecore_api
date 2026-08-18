"""Unit tests for the identifier rendering in the HTML serializer.

Exercises _identifier_values directly so the ISBN/LCCN behavior is covered
regardless of which rdf:value key form the stored JSON-LD uses.
"""

from bluecore_api.app.utils.serialize.html import (
    WORK_FIELDS,
    _admin_metadata_fields,
    _build_fields,
    _identifier_values,
    _rdf_value,
    _source_record_url,
    _title_of,
)

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


def test_rdf_value_prefers_available_key_form():
    assert _rdf_value({"rdf:value": "a"}) == "a"
    assert _rdf_value({RDF_VALUE_URI: "b"}) == "b"
    assert _rdf_value({"@type": "Isbn"}) is None


# --- titles ------------------------------------------------------------------
#
# bf:title carries the title proper and any variants together, told apart only by
# the node's type. They get separate headings, the way LC's own views do.


def _fields(data):
    return {
        field["label"]: [v["text"] for v in field["values"]]
        for field in _build_fields(data, WORK_FIELDS, {})
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


def test_title_of_ignores_variants():
    """
    The heading and any link naming the resource use the title proper, rather
    than joining every title the record carries.
    """
    assert _title_of(VARIANT_AND_PRIMARY) == "1,000 best movies on DVD"


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


def test_title_of_still_falls_back_to_aap():
    """A record with no title at all is still named by its access point."""
    assert _title_of({"bflc:aap": "Author, A. Some work"}) == "Author, A. Some work"


# --- derivedFrom -------------------------------------------------------------


def _admin_values(block):
    fields = _admin_metadata_fields(block)
    return [v for f in fields for v in f["values"]]


def test_source_record_url_points_at_the_lc_html_page():
    """id.loc.gov serves its readable page at .html, over https."""
    assert (
        _source_record_url("http://id.loc.gov/resources/works/23960506")
        == "https://id.loc.gov/resources/works/23960506.html"
    )


def test_source_record_url_is_idempotent():
    assert (
        _source_record_url("https://id.loc.gov/resources/works/23960506.html")
        == "https://id.loc.gov/resources/works/23960506.html"
    )


def test_source_record_url_leaves_other_hosts_alone():
    """We only know the .html convention for LC, so anything else links as-is."""
    other = "https://api.sinopia.io/resource/abc123"
    assert _source_record_url(other) == other


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
