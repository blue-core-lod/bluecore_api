"""Unit tests for the model-backed views: views/model.py, and the contribution
builder in views/fields.py that reads from it."""

import copy
import logging

from bluecore_models.models import Hub, Instance, Work
from bluecore_models.utils.graph import framed_for_storage

from bluecore_api.app.views import fields, model, nodes
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


def test_a_context_bibframe_json_does_not_ship_is_read_as_stored(caplog):
    """Most likely a newer version, written before this deploy caught up.
    Framing cannot read it, so its terms are taken at their current meaning,
    and the model says so, for the page to pass on."""
    data = {
        "@context": "https://bibframe-json.org/v9.9/context/bibframe.jsonld",
        "title": [{"mainTitle": ["The gunslinger"]}],
    }
    with caplog.at_level(logging.WARNING):
        resource = model.read(bibframe.Work, data, "https://x/1")
    assert resource is not None
    assert resource.read_as_stored
    assert fields.title_of(resource) == "The gunslinger"
    assert "so it is read as stored" in caplog.text


def test_read_gives_none_only_for_data_that_is_no_record():
    assert model.read(bibframe.Work, [{"@id": "https://x/1"}], "https://x/1") is None


# A record the reframe DAG has not reached yet. bibframe-json ships one version
# so far, so the only older form there is to test with is the one stored before
# rows named a context at all: no @context, and bare values where lists belong.
LEGACY = {
    "@id": "https://x/1",
    "@type": "Work",
    "title": {"mainTitle": "The gunslinger", "subtitle": "The dark tower I"},
    "contribution": {"agent": {"@id": AGENT}, "role": {"@id": AUTHOR}},
}


def test_read_frames_a_record_the_backfill_has_not_reached(caplog):
    with caplog.at_level(logging.INFO):
        resource = model.read(bibframe.Work, LEGACY, "https://x/1")
    assert resource is not None
    assert fields.title_of(resource) == "The gunslinger"
    assert "so it is framed to read" in caplog.text


def test_a_record_reads_the_same_before_and_after_the_backfill():
    """What the page shows mid-sweep is what it will show once the DAG has
    reframed the row, since both go through framed_for_storage."""
    reframed = framed_for_storage("https://x/1", LEGACY)
    assert reframed["@context"] == bibframe.CURRENT_CONTEXT
    labels = {AGENT: "King, Stephen, 1947-", AUTHOR: "author"}

    before = model.read(bibframe.Work, LEGACY, "https://x/1")
    after = model.read(bibframe.Work, reframed, "https://x/1")
    assert before is not None and after is not None

    built = fields.build_fields(after, labels)
    assert [f["label"] for f in built] == ["Title", "Subtitle", "Contribution"]
    assert fields.build_fields(before, labels) == built
    assert fields.title_of(before) == fields.title_of(after)


def test_framing_to_read_leaves_the_stored_row_as_it_is():
    """The row still says which context it was stored with, for anything that
    wants to know, and the DAG still finds it to reframe."""
    record = _record(Work, {**LEGACY, "@id": "https://bcld.info/x/1"})
    stored = copy.deepcopy(record.data)

    assert model.as_model(record) is not None

    assert record.data == stored


def test_a_record_that_frames_is_not_marked_as_read_as_stored():
    current = model.read(bibframe.Work, {"@context": CONTEXT_URL}, "https://x/1")
    legacy = model.read(bibframe.Work, LEGACY, "https://x/1")
    assert current is not None and legacy is not None
    assert not current.read_as_stored
    assert not legacy.read_as_stored


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


# --- cases from the review of #362 --------------------------------------------
#
# Each builds its record by hand rather than through the ORM. Framing on write
# makes four of these impossible in a framed record -- a null, a bare value
# where a list belongs, rdf:value under its full IRI, an empty list. A record
# read as stored, because framing cannot read its context, gets no such
# cleanup, so the reader is held to coping with them here.

UUID = "00000000-0000-4000-8000-000000000000"
URI = f"https://bcld.info/works/{UUID}"
N12345 = "http://id.loc.gov/rwo/agents/n12345"
PATHS: dict[type[bibframe.Resource], str] = {
    bibframe.Hub: "hubs",
    bibframe.Work: "works",
}


def _read(of: type[bibframe.Resource] = bibframe.Work, **properties):
    uri = f"https://bcld.info/{PATHS[of]}/{UUID}"
    resource = model.read(
        of,
        {
            "@context": bibframe.CURRENT_CONTEXT,
            "@id": uri,
            "@type": [of.__name__],
            **properties,
        },
        uri,
    )
    assert resource is not None
    return resource


def test_an_agent_named_by_its_bflc_authoritative_label_keeps_its_name():
    resource = _read(
        contribution=[
            {"agent": [{"@id": N12345, "bflc:authoritativeLabel": ["King, Stephen"]}]}
        ]
    )

    values = fields.contribution_values(resource.contribution, {})

    assert [v["text"] for v in values] == ["King, Stephen"]


def test_an_unmodelled_node_named_by_its_main_title_keeps_its_title():
    resource = _read(
        relatedTo=[
            {
                "@id": "https://bcld.info/works/other",
                "mainTitle": ["The drawing of the three"],
            }
        ]
    )

    [related] = resource.values("relatedTo")

    assert nodes.value_text(related) == "The drawing of the three"


def test_a_malformed_unmodelled_property_costs_only_its_own_field(caplog):
    """Unmodelled properties are checked as they are read, so a bad one is left
    out there rather than failing the page. Framing drops a null on write."""
    resource = _read(title=[{"mainTitle": ["The gunslinger"]}], extent=[None])

    built = fields.build_fields(resource, {})

    assert "The gunslinger" in str(built)
    assert "Extent" not in [f["label"] for f in built]
    assert "leaving out extent" in caplog.text


def test_one_malformed_title_does_not_drop_the_others():
    """Only the bad item of a list is left out. Framing makes a bare value a
    list on write."""
    resource = _read(
        title=[{"mainTitle": ["The gunslinger"]}, {"mainTitle": "Gunslinger"}]
    )

    assert fields.title_of(resource) == "The gunslinger"


def test_an_identifier_value_under_its_full_iri_still_shows():
    """Framing compacts rdf:value on write; the full IRI reads all the same."""
    resource = _read(
        identifiedBy=[{"@type": ["Lccn"], bibframe.RDF_VALUE: ["2003064574"]}]
    )

    values = fields.identifier_values(resource.identified_by, {})

    assert [v["text"] for v in values] == ["2003064574"]


def test_a_literal_note_keeps_its_text():
    resource = _read(note=["Includes index"])

    values = fields.note_values(resource.note, {})

    assert [v["text"] for v in values] == ["Includes index"]


def test_a_literal_note_on_a_title_keeps_its_text():
    resource = _read(title=[{"note": ["English summary title"]}])

    assert fields.title_of(resource) == "English summary title"


def test_a_hub_with_an_empty_label_is_named_by_its_authoritative_label():
    """An empty property names nothing, so the next one gets its turn. Framing
    drops an empty list on write."""
    resource = _read(
        bibframe.Hub,
        **{"rdfs:label": [], "mads:authoritativeLabel": ["Dark tower"]},
    )

    assert fields.title_of(resource) == "Dark tower"


def test_a_term_with_an_empty_label_is_named_by_its_authoritative_label():
    resource = _read(
        subject=[
            {
                "@id": "http://id.worldcat.org/fast/1234",
                "rdfs:label": [],
                "mads:authoritativeLabel": ["Gunslingers"],
            }
        ]
    )

    values = fields.authority_values(resource.subject, {})

    assert values[0]["text"] == "Gunslingers"


def test_a_value_stated_twice_reads_once():
    """526 stage pages showed a title or name doubled: "Feng, Zongze, Feng,
    Zongze"."""
    resource = _read(
        contribution=[{"agent": [{"rdfs:label": ["Feng, Zongze", "Feng, Zongze"]}]}]
    )

    values = fields.contribution_values(resource.contribution, {})

    assert [v["text"] for v in values] == ["Feng, Zongze"]
