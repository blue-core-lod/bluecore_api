"""Unit tests for views/search_display.py -- naming and other logic for search.
"""

from bluecore_models.models import Hub, Instance, OtherResource, Work

from bluecore_api.app.views.search_display import (
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