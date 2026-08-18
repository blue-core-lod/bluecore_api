"""Unit tests for views/nodes.py -- reading json-ld nodes into text.

Which rdf:value form a node uses, which of several titles names the record, and
how a source record's readable page is addressed.
"""

from bluecore_api.app.views.nodes import (
    _rdf_value,
    _source_record_url,
    _title_of,
)

RDF_VALUE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"


def test_rdf_value_prefers_available_key_form():
    assert _rdf_value({"rdf:value": "a"}) == "a"
    assert _rdf_value({RDF_VALUE_URI: "b"}) == "b"
    assert _rdf_value({"@type": "Isbn"}) is None


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


def test_title_of_ignores_variants():
    """
    The heading and any link naming the resource use the title proper, rather
    than joining every title the record carries.
    """
    assert _title_of(VARIANT_AND_PRIMARY) == "1,000 best movies on DVD"


def test_title_of_still_falls_back_to_aap():
    """A record with no title at all is still named by its access point."""
    assert _title_of({"bflc:aap": "Author, A. Some work"}) == "Author, A. Some work"


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
