"""Unit tests for views/sidebar.py -- how a record links to its neighbors.

These run without a database. relation_sections falls back to the labels a
record's own json-ld carries when there is no session to resolve targets in,
which is exactly the path that matters here: the grouping, the headings and the
linking, separately from the lookup (covered in tests/api).
"""

from bluecore_models.models import Hub, Instance, Work

from bluecore_api.app.views.sidebar import (
    _instance_label,
    _record_label,
    add_section,
    record_link,
    relation_sections,
    works_for_hub,
)

SERIES = "http://id.loc.gov/vocabulary/relationship/series"
SERIES_OF = "http://id.loc.gov/vocabulary/relationship/seriesof"
TRANSLATED_AS = "http://id.loc.gov/vocabulary/relationship/translatedas"


def _sections(data):
    work = Work(
        uri="http://localhost/works/x", data={**data, "@id": "http://localhost/works/x"}
    )
    return {s["label"]: s["values"] for s in relation_sections(work, {})}


# --- naming an Instance ------------------------------------------------------


def test_instance_label_prefers_the_publication_statement():
    """Every Instance of a Work shares its title, so the imprint is what tells
    two of them apart -- LC's "Has Instance" reads this way."""
    data = {
        "title": {"mainTitle": "Minority voices"},
        "publicationStatement": "Hershey, PA: IGI Global, [2025]",
    }
    assert _instance_label(data) == "Hershey, PA: IGI Global, [2025]"


def test_instance_label_assembles_the_provision_activity():
    data = {
        "title": {"mainTitle": "Minority voices"},
        "provisionActivity": {
            "@type": ["ProvisionActivity", "Publication"],
            "bflc:simplePlace": "Hershey, PA",
            "bflc:simpleAgent": "IGI Global",
            "bflc:simpleDate": "[2025]",
        },
    }
    assert _instance_label(data) == "Hershey, PA: IGI Global, [2025]"


def test_instance_label_copes_with_a_partial_provision_activity():
    data = {"provisionActivity": {"bflc:simplePlace": "Hershey, PA"}}
    assert _instance_label(data) == "Hershey, PA"


def test_instance_label_falls_back_to_the_title():
    """No imprint at all: better the title than an empty line."""
    assert _instance_label({"title": {"mainTitle": "The waste lands"}}) == (
        "The waste lands"
    )


# --- naming any record ------------------------------------------------------


def test_record_label_uses_the_imprint_for_instances_and_the_access_point_otherwise():
    instance = Instance(
        uri="http://localhost/instances/i",
        data={
            "@id": "http://localhost/instances/i",
            "title": {"mainTitle": "The waste lands"},
            "publicationStatement": "New York: Plume, c1991",
        },
    )
    work = Work(
        uri="http://localhost/works/w",
        data={
            "@id": "http://localhost/works/w",
            "title": {"mainTitle": "The waste lands"},
            "bflc:aap": "King, Stephen, 1947-. The waste lands",
        },
    )

    assert _record_label(instance) == "New York: Plume, c1991"
    assert _record_label(work) == "King, Stephen, 1947-. The waste lands"


def test_record_link_carries_the_records_own_uri():
    hub = Hub(
        uri="http://localhost/hubs/h",
        data={
            "@id": "http://localhost/hubs/h",
            "rdfs:label": "King, Stephen. Dark tower",
        },
    )

    assert record_link(hub) == {
        "text": "King, Stephen. Dark tower",
        "href": "http://localhost/hubs/h",
        "internal": True,
    }


# --- sections ---------------------------------------------------------------


def test_add_section_folds_into_an_open_section_of_the_same_name():
    """A transcribed seriesStatement and a bf:relation both belong under Series."""
    sidebar = [{"label": "Series", "values": [{"text": "a", "href": None}]}]

    add_section(sidebar, "Series", [{"text": "b", "href": None}])

    assert len(sidebar) == 1
    assert [v["text"] for v in sidebar[0]["values"]] == ["a", "b"]


def test_add_section_drops_a_value_already_in_the_section():
    sidebar = [{"label": "Series", "values": [{"text": "a", "href": None}]}]

    add_section(sidebar, "Series", [{"text": "a", "href": None}])

    assert len(sidebar[0]["values"]) == 1


def test_add_section_appends_a_new_heading():
    sidebar = [{"label": "Series", "values": [{"text": "a", "href": None}]}]

    add_section(sidebar, "Has Instance", [{"text": "b", "href": None}])

    assert [s["label"] for s in sidebar] == ["Series", "Has Instance"]


# --- relation sections ------------------------------------------------------


def test_no_relations_means_no_sections():
    assert relation_sections(Work(uri="http://localhost/works/x", data={}), {}) == []


def test_relations_group_under_their_relationship():
    sections = _sections(
        {
            "relation": [
                {
                    "relationship": {"@id": SERIES_OF},
                    "associatedResource": {
                        "@id": "http://localhost/works/a",
                        "bflc:aap": "A",
                    },
                },
                {
                    "relationship": {"@id": SERIES_OF},
                    "associatedResource": {
                        "@id": "http://localhost/works/b",
                        "bflc:aap": "B",
                    },
                },
                {
                    "relationship": {"@id": TRANSLATED_AS},
                    "associatedResource": {
                        "@id": "http://localhost/hubs/c",
                        "bflc:aap": "C",
                    },
                },
            ]
        }
    )

    assert list(sections) == ["Series of", "Translated as"]
    assert len(sections["Series of"]) == 2
    assert len(sections["Translated as"]) == 1


def test_a_transcribed_series_statement_has_no_link():
    """It carries no uri of its own, so it is plain text, as on LC's page."""
    sections = _sections(
        {
            "relation": {
                "relationship": {"@id": SERIES},
                "seriesEnumeration": "4",
                "associatedResource": {
                    "@type": ["Series", "bflc:Uncontrolled"],
                    "title": {"mainTitle": "The dark tower"},
                },
            }
        }
    )

    (value,) = sections["Series"]
    assert value["text"] == "The dark tower 4"
    assert value["href"] is None


def test_an_lc_target_links_to_its_readable_page_in_a_new_tab():
    lc_hub = "http://id.loc.gov/resources/hubs/4403fbce"
    sections = _sections(
        {
            "relation": {
                "relationship": {"@id": SERIES},
                "associatedResource": {"@id": lc_hub, "rdfs:label": "Dark tower"},
            }
        }
    )

    (value,) = sections["Series"]
    assert value["href"] == "https://id.loc.gov/resources/hubs/4403fbce.html"
    assert value["external"] is True


def test_a_blue_core_target_links_as_it_stands():
    sections = _sections(
        {
            "relation": {
                "relationship": {"@id": SERIES},
                "associatedResource": {
                    "@id": "http://localhost/hubs/h",
                    "rdfs:label": "Dark tower",
                },
            }
        }
    )

    (value,) = sections["Series"]
    assert value["href"] == "http://localhost/hubs/h"
    assert "external" not in value


def test_an_oclc_work_identity_is_not_a_sidebar_section():
    """OCLC states which WorldCat entity a Work is, as a bf:Relation. That is an
    identity, not a link, and its target is an opaque id with nothing to show."""
    sections = _sections(
        {
            "relation": {
                "@type": "Relation",
                "relationship": {
                    "@id": "https://id.oclc.org/worldcat/ontology/hasWork"
                },
                "associatedResource": {
                    "@id": "https://id.oclc.org/worldcat/entity/E39PCGdHPPTXB7wyDxfp7hTxH3"
                },
            }
        }
    )

    assert sections == {}


def test_an_oclc_identity_does_not_suppress_a_real_relation_beside_it():
    """Only the identity relation drops out; the record's other links stay."""
    sections = _sections(
        {
            "relation": [
                {
                    "relationship": {
                        "@id": "https://id.oclc.org/worldcat/ontology/hasWork"
                    },
                    "associatedResource": {
                        "@id": "https://id.oclc.org/worldcat/entity/E39PCG"
                    },
                },
                {
                    "relationship": {"@id": SERIES},
                    "associatedResource": {
                        "@id": "http://localhost/hubs/h",
                        "rdfs:label": "Dark tower",
                    },
                },
            ]
        }
    )

    assert list(sections) == ["Series"]
    assert sections["Series"][0]["text"] == "Dark tower"


def test_works_for_hub_is_empty_when_nothing_links_back():
    """A Hub no Work's foreign key names has no Works; that is empty, not an error."""
    assert works_for_hub(Hub(uri="http://localhost/hubs/h", data={})) == []
