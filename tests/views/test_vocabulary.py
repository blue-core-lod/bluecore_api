"""Unit tests for views/vocabulary.py -- turning uris into readable words.

The layer the recent view bugs actually lived in: a record references a term by
uri and leaves the label behind, so a gap here shows up as "n79063767 (ctb)" or
"Otherphysicalformat, onlineversion" on the page.
"""

from bluecore_models.models import BibframeOtherResources, OtherResource, Work

from bluecore_api.app.views import vocabulary
from bluecore_api.app.views.vocabulary import (
    NOTE_TYPE_LABELS,
    RELATIONSHIP_LABELS,
    RELATOR_LABELS,
    _relationship_words,
    build_label_map,
    relationship_labels,
    resolve_label,
    section_order,
)

RELATIONSHIP = "http://id.loc.gov/vocabulary/relationship/"
ONLINE_VERSION = "http://id.loc.gov/entities/relationships/onlineversion"
AGENT = "http://id.loc.gov/rwo/agents/n79063767"


# --- the label map -----------------------------------------------------------


def _work_citing(term_uri, term_data):
    """A Work with one OtherResource attached, built without touching a session."""
    work = Work(
        uri="http://localhost/works/x", data={"@id": "http://localhost/works/x"}
    )
    other = OtherResource(uri=term_uri, data=term_data)
    work.other_resources.append(BibframeOtherResources(other_resource=other))
    return work


def test_label_map_reads_rdfs_label():
    work = _work_citing(
        AGENT, {"@id": AGENT, "@type": "Agent", "rdfs:label": "King, Stephen, 1947-"}
    )
    assert build_label_map(work)[AGENT] == "King, Stephen, 1947-"


def test_label_map_reads_an_authoritative_label():
    """Authorities carry madsrdf:authoritativeLabel rather than rdfs:label."""
    uri = "http://id.loc.gov/authorities/subjects/sh2010111410"
    work = _work_citing(
        uri,
        {
            "@id": uri,
            "@type": "mads:Topic",
            "mads:authoritativeLabel": "Roland (Fictitious character)",
        },
    )
    assert build_label_map(work)[uri] == "Roland (Fictitious character)"


def test_label_map_skips_a_term_with_no_label():
    """A bf:Role carries a code and nothing else -- there is no label to find,
    which is why RELATOR_LABELS exists."""
    ctb = f"{RELATIONSHIP.replace('relationship/', '')}relators/ctb"
    work = _work_citing(ctb, {"@id": ctb, "@type": "Role", "code": "ctb"})
    assert ctb not in build_label_map(work)


def test_label_map_survives_an_unreadable_other_resource(monkeypatch):
    """One unparseable attachment should not take the whole page down with it."""
    work = _work_citing(AGENT, {"@id": AGENT, "rdfs:label": "Fine"})

    def explode(_data):
        raise ValueError("unparseable json-ld")

    monkeypatch.setattr(vocabulary, "load_jsonld", explode)

    assert build_label_map(work) == {}


# --- resolving a value's own text against the map ----------------------------


def test_resolve_label_prefers_text_the_node_already_carries():
    label_map = {AGENT: "From the map"}
    assert resolve_label(AGENT, "Embedded label", label_map) == "Embedded label"


def test_resolve_label_fills_in_a_bare_reference():
    """A bare {"@id": ...} renders as its uri tail until the map supplies a label."""
    label_map = {AGENT: "King, Stephen, 1947-"}
    assert resolve_label(AGENT, "n79063767", label_map) == "King, Stephen, 1947-"


def test_resolve_label_leaves_the_tail_when_the_map_has_nothing():
    assert resolve_label(AGENT, "n79063767", {}) == "n79063767"


# --- relationship headings ---------------------------------------------------


def _relation(*terms):
    return {"relationship": [{"@id": t} for t in terms]}


def test_relationship_label_uses_lcs_wording_for_a_run_together_slug():
    """These slugs cannot be split by rule, so the table carries LC's spelling."""
    assert relationship_labels(_relation(f"{RELATIONSHIP}seriesof"), {}) == [
        "Series of"
    ]
    assert relationship_labels(_relation(f"{RELATIONSHIP}relatedwork"), {}) == [
        "Related work"
    ]
    assert relationship_labels(_relation(f"{RELATIONSHIP}translatedas"), {}) == [
        "Translated as"
    ]


def test_relationship_label_prefers_a_vocabulary_label_we_hold():
    term = f"{RELATIONSHIP}series"
    assert relationship_labels(_relation(term), {term: "series"}) == ["Series"]


def test_relationship_label_falls_back_to_related():
    assert relationship_labels({}, {}) == ["Related"]


def test_relationship_words_spaces_a_slug_it_can_read():
    assert _relationship_words("precededby") == "Preceded by"
    assert _relationship_words("issuedwith") == "Issued with"
    assert _relationship_words("hasSeries") == "Has series"


def test_relationship_words_leaves_a_word_it_cannot_split():
    """Better an unsplit heading than "Describe s" -- the table is the fix."""
    assert _relationship_words("describes") == "Describes"
    assert _relationship_words("indexes") == "Indexes"


# --- section order -----------------------------------------------------------


def test_section_order_follows_lcs_hub_page():
    labels = ["Series of", "Related work", "Part of", "Translated as", "Related To"]
    assert [section_order(x) for x in labels] == sorted(
        section_order(x) for x in labels
    )


def test_unlisted_sections_sort_after_the_known_ones():
    """A heading the table does not carry -- from _relationship_words -- follows
    every heading it does."""
    assert section_order("Preceded by") > section_order("Related To")
    assert section_order("Has series") > section_order("Series of")


# --- the curated tables ------------------------------------------------------


def test_curated_tables_are_keyed_by_bare_code_or_slug():
    """Lookups pass a uri tail, so a key with a slash or colon would never hit."""
    for table in (RELATOR_LABELS, NOTE_TYPE_LABELS, RELATIONSHIP_LABELS):
        for key, label in table.items():
            assert "/" not in key and ":" not in key, key
            assert label and label == label.strip(), key
