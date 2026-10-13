"""Unit tests for the model-backed views: views/model.py, and the contribution
builder in views/fields.py that reads from it."""

import logging

from bluecore_models.models import Hub, Instance, Work

from bluecore_api.app.views import fields, model
from bluecore_api.constants import CONTEXT_URL
from bluecore_api.schemas import bibframe

AUTHOR = "http://id.loc.gov/vocabulary/relators/aut"
AGENT = "http://id.loc.gov/rwo/agents/n79063767"


def _contributions(*items: dict) -> list[bibframe.Contribution]:
    return bibframe.Work.model_validate({"contribution": list(items)}).contribution


def test_an_agent_cited_by_uri_is_named_from_the_vocabulary():
    values = fields.contribution_values(
        _contributions({"agent": [{"@id": AGENT}], "role": [{"@id": AUTHOR}]}),
        {AGENT: "King, Stephen, 1947-", AUTHOR: "author"},
    )
    assert values == [
        {
            "text": "King, Stephen, 1947-",
            "href": AGENT,
            "internal": False,
            "suffixes": [{"text": "author", "href": AUTHOR}],
        }
    ]


def test_an_agent_described_in_place_keeps_its_own_label():
    """A blank node carries its label, in a plain string or a value object."""
    values = fields.contribution_values(
        _contributions(
            {
                "agent": [
                    {
                        "@type": ["Person"],
                        "rdfs:label": [
                            "Chakravorti, Madhavadas",
                            {"@value": "Чакраворти", "@language": "ru"},
                        ],
                    }
                ],
                "role": [{"@type": ["Role"], "rdfs:label": ["ill."]}],
            }
        ),
        {},
    )
    assert values == [
        {
            "text": "Chakravorti, Madhavadas, Чакраворти",
            "href": None,
            "internal": False,
            "suffixes": [{"text": "ill.", "href": None}],
        }
    ]


def test_an_agent_with_no_label_falls_back_to_its_uri_tail():
    values = fields.contribution_values(_contributions({"agent": [AGENT]}), {})
    assert [(v["text"], v["href"]) for v in values] == [("n79063767", AGENT)]


def test_a_role_with_nothing_to_show_adds_no_suffix():
    values = fields.contribution_values(
        _contributions({"agent": [{"@id": AGENT}], "role": [{"@type": ["Role"]}]}),
        {},
    )
    assert "suffixes" not in values[0]


def test_only_the_first_role_shows():
    """Matches the dict builder; 3% of contributions on stage carry more."""
    values = fields.contribution_values(
        _contributions(
            {"agent": [{"@id": AGENT}], "role": [{"@id": AUTHOR}, {"@id": "x:ill"}]}
        ),
        {},
    )
    assert values[0]["suffixes"] == [{"text": "aut", "href": AUTHOR}]


def _record(cls, data):
    return cls(uri="https://bcld.info/x/1", data=data)


def test_as_model_reads_each_record_as_its_own_class():
    data = {"@context": bibframe.CURRENT_CONTEXT, "@type": ["Work", "Hub"]}
    assert type(model.as_model(_record(Hub, data))) is bibframe.Hub
    assert type(model.as_model(_record(Work, data))) is bibframe.Work
    assert type(model.as_model(_record(Instance, data))) is bibframe.Instance


def test_read_refuses_another_context(caplog):
    """A row a backfill missed is read as a dict, and logged, not guessed at."""
    data = {"@context": "https://bibframe-json.org/v0.0/context/bibframe.jsonld"}
    with caplog.at_level(logging.WARNING):
        assert model.read(bibframe.Work, data, "https://x/1") is None
    assert "not the current one" in caplog.text


def test_read_takes_the_bluecore_context_as_the_current_one():
    """What a client round-tripping one of our records sends back."""
    data = {"@context": CONTEXT_URL}
    assert model.read(bibframe.Work, data, "https://x/1") is not None


def test_read_leaves_out_only_the_property_that_will_not_read(caplog):
    """One malformed property costs the page that field, and no other."""
    data = {
        "@context": bibframe.CURRENT_CONTEXT,
        "title": [{"mainTitle": ["Dark tower"]}],
        "contribution": [{"agent": [5]}],
    }
    resource = model.read(bibframe.Work, data, "https://x/1")
    assert resource is not None
    assert [str(t) for t in resource.title[0].main] == ["Dark tower"]
    assert resource.contribution == []
    assert "leaving out contribution" in caplog.text
