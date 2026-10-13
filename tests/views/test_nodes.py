"""Unit tests for views/nodes.py -- naming and linking a value, and the uri
helpers.

Each way a value names itself, in the order they win, and how a source
record's readable page is addressed.
"""

from bluecore_api.app.views.nodes import (
    source_record_url,
    split_camel_case,
    value_href,
    value_text,
)
from bluecore_api.schemas import bibframe

ENG = "http://id.loc.gov/vocabulary/languages/eng"


def _node(data):
    return bibframe.Ref.model_validate(data)


def test_a_literal_is_its_own_text():
    assert value_text(bibframe.Text.model_validate("24 cm")) == "24 cm"
    assert (
        value_text(bibframe.Text.model_validate({"@value": "x", "@language": "en"}))
        == "x"
    )


def test_a_node_is_named_by_its_label():
    assert value_text(_node({"@id": ENG, "rdfs:label": ["English"]})) == "English"


def test_a_label_can_itself_be_a_reference():
    """Some nodes on stage name themselves by pointing at a term."""
    assert value_text(_node({"rdfs:label": [{"@id": ENG}]})) == "eng"


def test_a_node_without_a_label_is_named_by_its_rdf_value():
    assert (
        value_text(_node({"@type": ["AspectRatio"], "rdf:value": [" 16:9 "]})) == "16:9"
    )


def test_a_node_without_a_label_or_value_is_named_by_its_note():
    """As 6,593 capture and supplementaryContent nodes on stage are."""
    node = _node(
        {
            "@type": ["Capture"],
            "note": [{"@type": ["Note"], "rdfs:label": ["Recorded live"]}],
        }
    )
    assert value_text(node) == "Recorded live"


def test_a_node_with_only_a_code_is_named_by_it():
    assert value_text(_node({"@type": ["Status"], "code": ["incmp"]})) == "incmp"


def test_a_bare_reference_is_named_by_its_uri_tail():
    assert value_text(_node({"@id": ENG})) == "eng"


def test_a_node_with_nothing_to_show_is_empty():
    assert value_text(_node({"@type": ["Ensemble"], "ensembleSize": ["4"]})) == ""


def test_a_value_links_to_its_own_uri_or_its_locator():
    assert value_href(_node({"@id": ENG})) == ENG
    locator = "https://example.org/toc.pdf"
    assert value_href(_node({"electronicLocator": [locator]})) == locator
    assert value_href(_node({"@id": "_:b1"})) is None
    assert value_href(bibframe.Text.model_validate("24 cm")) is None


def test_source_record_url_points_at_the_lc_html_page():
    """id.loc.gov serves its readable page at .html, over https."""
    assert (
        source_record_url("http://id.loc.gov/resources/works/23960506")
        == "https://id.loc.gov/resources/works/23960506.html"
    )


def test_source_record_url_is_idempotent():
    assert (
        source_record_url("https://id.loc.gov/resources/works/23960506.html")
        == "https://id.loc.gov/resources/works/23960506.html"
    )


def test_source_record_url_leaves_other_hosts_alone():
    """We only know the .html convention for LC, so anything else links as-is."""
    other = "https://api.sinopia.io/resource/abc123"
    assert source_record_url(other) == other


def test_split_camel_case_spaces_a_run_together_type():
    """Type values arrive as one word: "MovingImage" should read "Moving Image"."""
    assert split_camel_case("MovingImage") == "Moving Image"
    assert split_camel_case("NotatedMusic") == "Notated Music"
    assert split_camel_case("NonMusicAudio") == "Non Music Audio"


def test_split_camel_case_leaves_single_words_and_acronyms_alone():
    for word in ("Hub", "Text", "Monograph", "Series", "LCCN"):
        assert split_camel_case(word) == word


def test_split_camel_case_keeps_an_acronym_whole_before_a_word():
    assert split_camel_case("PDFDocument") == "PDF Document"
