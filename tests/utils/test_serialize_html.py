"""Unit tests for the identifier rendering in the HTML serializer.

Exercises _identifier_values directly so the ISBN/LCCN behavior is covered
regardless of which rdf:value key form the stored JSON-LD uses.
"""

from bluecore_api.app.utils.serialize.html import _identifier_values, _rdf_value

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
