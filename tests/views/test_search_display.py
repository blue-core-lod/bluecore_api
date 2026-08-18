"""Unit tests for views/search_display.py -- naming and grouping for search.

resource_title backs the search results list. resource_section groups
OtherResources -- authorities, vocabularies, classifications -- by the RDF type
they carry; it has no caller yet (OtherResources are excluded from search pending
feedback), so these tests pin the contract rather than a rendered page.
"""

from bluecore_models.models import Hub, Instance, OtherResource, Work

from bluecore_api.app.views.search_display import (
    OTHER_SECTION_ORDER,
    resource_section,
    resource_title,
)

BF = "http://id.loc.gov/ontologies/bibframe/"


def _other(*types):
    uri = "https://id.loc.gov/x/thing"
    return OtherResource(uri=uri, data={"@id": uri, "@type": list(types)})


# --- resource_title ----------------------------------------------------------


def test_resource_title_uses_the_title_proper():
    work = Work(
        uri="http://localhost/works/w",
        data={
            "@id": "http://localhost/works/w",
            "title": [
                {"@type": "VariantTitle", "mainTitle": "Wizard & glass"},
                {"@type": "Title", "mainTitle": "Wizard and glass"},
            ],
        },
    )
    assert resource_title(work) == "Wizard and glass"


def test_resource_title_falls_back_to_the_access_point():
    hub = Hub(
        uri="http://localhost/hubs/h",
        data={
            "@id": "http://localhost/hubs/h",
            "bflc:aap": "King, Stephen. Dark tower",
        },
    )
    assert resource_title(hub) == "King, Stephen. Dark tower"


def test_resource_title_of_an_untitled_record_is_empty_not_an_error():
    """A result with nothing to name it still has to come back a string, so the
    search list renders a row rather than raising."""
    instance = Instance(
        uri="http://localhost/instances/i", data={"@id": "http://localhost/instances/i"}
    )
    assert resource_title(instance) == ""


# --- resource_section --------------------------------------------------------


def test_agents_and_names_share_one_section():
    for bf_type in ("Person", "Organization", "Family", "Meeting", "Agent"):
        assert resource_section(_other(f"{BF}{bf_type}")) == "Name Authorities", bf_type


def test_mads_name_types_land_in_the_same_section_as_their_bf_equivalents():
    """madsrdf and bibframe name the same thing differently; the reader should
    not see two headings for it."""
    assert resource_section(_other("mads:PersonalName")) == "Name Authorities"
    assert resource_section(_other("mads:CorporateName")) == "Name Authorities"


def test_subjects_genres_classifications_and_hubs_each_have_a_section():
    assert resource_section(_other(f"{BF}Topic")) == "Subjects"
    assert resource_section(_other(f"{BF}GenreForm")) == "Genres & Forms"
    assert resource_section(_other(f"{BF}ClassificationLcc")) == "LC Classifications"
    assert resource_section(_other(f"{BF}ClassificationDdc")) == "Classifications"
    assert resource_section(_other(f"{BF}Hub")) == "Hubs"
    assert resource_section(_other(f"{BF}Language")) == "Vocabularies"


def test_the_first_recognised_type_wins():
    """Records carry several types; the section comes from the one we know."""
    assert resource_section(_other(f"{BF}Unknown", f"{BF}Topic")) == "Subjects"


def test_an_unrecognised_type_gets_a_section_of_its_own():
    """Rather than a catch-all, so a new kind is visible instead of buried."""
    assert resource_section(_other(f"{BF}Fixture")) == "Fixtures"
    assert resource_section(_other(f"{BF}Prophecy")) == "Prophecies"
    assert resource_section(_other(f"{BF}Box")) == "Boxes"


def test_a_type_that_is_already_plural_is_left_alone():
    assert resource_section(_other(f"{BF}Series")) == "Series"


def test_a_record_with_no_type_falls_back():
    uri = "https://id.loc.gov/x/thing"
    assert resource_section(OtherResource(uri=uri, data={"@id": uri})) == (
        "Other Resources"
    )


def test_every_named_section_is_in_the_display_order():
    """A section missing from OTHER_SECTION_ORDER would sort with the unknowns,
    away from the group it belongs to."""
    from bluecore_api.app.views.search_display import _SECTION_BY_TYPE

    for section in set(_SECTION_BY_TYPE.values()):
        assert section in OTHER_SECTION_ORDER, section
