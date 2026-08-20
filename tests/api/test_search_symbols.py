"""End-to-end search tests for symbol normalization (#203).

Split out of test_search.py, which covers query syntax and paging. These go
through the HTTP endpoint against a real index, so they exercise the whole
path: framing on insert, the data_vector generated column, and the tsquery
built by search_tsquery.

Run just these with:

    uv run pytest -m symbols
"""

import json
import pathlib

import pytest
from bluecore_models.models import Work
from bluecore_models.utils.search import normalize_symbols
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bluecore_api.app.routes.search import format_query

pytestmark = pytest.mark.symbols

# Keyed by uuid, not a readable slug: uri is indexed into data_vector at weight
# C, so a slug like "symbol-test-flat" would contribute the token "flat" and make
# these assertions pass for the wrong reason.
FLAT = "e26cb16a-bff3-5170-889b-2d76f34e7ff9"
SHARP = "ed503446-4a40-52d1-b2af-729840d0955e"
NATURAL = "62ac5099-3d5d-583c-8641-e5b235d5e970"
COORDINATES = "7043cbf4-22e3-5738-b385-6ca34493cacd"
COPYRIGHT = "f5fd382d-2c18-59a8-aa45-63ed09094eee"
PHONOGRAM = "65a4f7d9-8ebd-51f3-b7f1-8716cc39c68c"
ROMANIZATION = "cb0e1827-c1bf-569e-982c-5085bfc6e89b"
LIGATURE = "509a82d1-7152-500f-9ca3-57d106c7d3f6"
DOUBLE_TILDE = "62521e5a-ccc9-5d1e-a1c4-0cd85f30eb57"
SUBSCRIPT = "ffe8e9b0-a108-56fe-ae8e-372f98d28d5e"
SUPERSCRIPT = "62942362-c428-5f72-a973-eaa7575766c7"
SCRIPT_SIGNS = "cb237475-28e0-5f1d-974d-90b1603d627a"
CONTROL = "02f4ae51-5042-564a-b4ec-503583570762"


def add_symbol_data(db_session: Session):
    """Load one record per row of the symbol table."""
    with pathlib.Path("tests/symbols.jsonld").open() as fo:
        records = json.load(fo)
    for offset, record in enumerate(records, start=100):
        uri = record["@id"]
        db_session.add(
            Work(id=offset, uuid=uri.rsplit("/", 1)[-1], uri=uri, data=record)
        )
    db_session.commit()


def search_uuids(client: TestClient, q: str) -> list[str]:
    response = client.get("/search/", params={"q": q})
    assert response.status_code == 200
    return [r["uri"].rsplit("/", 1)[-1] for r in response.json()["results"]]


def test_sharp_does_not_match_flat_record(client: TestClient, db_session: Session):
    """The bug reported in #203: the parser dropped the musical signs, so
    searching D-sharp returned the D-flat record."""
    add_symbol_data(db_session)

    assert FLAT not in search_uuids(client, "D♯ major")


def test_flat_matches_flat_record(client: TestClient, db_session: Session):
    add_symbol_data(db_session)

    assert FLAT in search_uuids(client, "D♭ major")


def test_sharp_matches_its_own_record(client: TestClient, db_session: Session):
    """Guards against the sentinel silently matching nothing at all, which would
    also make the test above pass."""
    add_symbol_data(db_session)

    assert SHARP in search_uuids(client, "F♯ minor")


def test_ascii_hash_finds_the_sharp_record(client: TestClient, db_session: Session):
    """Cataloguers type "F#" because keyboards have no U+266F. Both spellings
    must reach the same record."""
    add_symbol_data(db_session)

    assert SHARP in search_uuids(client, "F# minor")
    assert search_uuids(client, "F# minor") == search_uuids(client, "F♯ minor")


def test_ascii_b_finds_the_flat_record(client: TestClient, db_session: Session):
    """Cataloguers type "Db" because keyboards have no U+266D."""
    add_symbol_data(db_session)

    assert FLAT in search_uuids(client, "Db major")
    assert search_uuids(client, "Db major") == search_uuids(client, "D♭ major")


def test_ascii_b_in_ordinary_words_is_not_a_flat(
    client: TestClient, db_session: Session
):
    """Guarding b badly once put a flat token into 1043 of 1056 records,
    including every hex uuid in the database."""
    add_symbol_data(db_session)

    # Only the one seeded record carries a flat.
    assert len(search_uuids(client, "♭")) == 1


def test_ascii_hash_in_a_uri_is_not_a_sharp(client: TestClient, db_session: Session):
    """Every JSON-LD record contains XMLSchema#dateTime. If that counted as a
    sharp, a bare sharp search would return most of the database."""
    add_symbol_data(db_session)

    # Only the one seeded record carries a sharp.
    assert len(search_uuids(client, "♯")) == 1


def test_plain_letter_search_still_matches(client: TestClient, db_session: Session):
    """No regression: dropping the symbol must not stop "D major" matching."""
    add_symbol_data(db_session)

    assert FLAT in search_uuids(client, "D major")


def test_natural_sign(client: TestClient, db_session: Session):
    add_symbol_data(db_session)

    assert NATURAL in search_uuids(client, "B♮")


def test_romanization_mark_stripped(client: TestClient, db_session: Session):
    """Searching Sadi finds Saʻdī. Returned nothing before this change."""
    add_symbol_data(db_session)

    assert ROMANIZATION in search_uuids(client, "Sadi")


def test_romanization_mark_typed(client: TestClient, db_session: Session):
    """And typing the mark still works. This regressed when only the index was
    normalized: the index held "sadi" while the query split into "sa" + "di"."""
    add_symbol_data(db_session)

    assert ROMANIZATION in search_uuids(client, "Saʻdī")


def test_combining_ligature(client: TestClient, db_session: Session):
    add_symbol_data(db_session)

    assert LIGATURE in search_uuids(client, "transformatsii")


def test_double_tilde(client: TestClient, db_session: Session):
    add_symbol_data(db_session)

    assert DOUBLE_TILDE in search_uuids(client, "ngün")


def test_subscript_folding(client: TestClient, db_session: Session):
    add_symbol_data(db_session)

    assert SUBSCRIPT in search_uuids(client, "h2o")
    assert SUBSCRIPT in search_uuids(client, "c6h12o6")


def test_subscript_typed(client: TestClient, db_session: Session):
    add_symbol_data(db_session)

    assert SUBSCRIPT in search_uuids(client, "H₂O")


def test_superscript_folding(client: TestClient, db_session: Session):
    add_symbol_data(db_session)

    assert SUPERSCRIPT in search_uuids(client, "x2")
    assert SUPERSCRIPT in search_uuids(client, "x² + y²")


def test_parenthesis_forms_do_not_break_the_query(
    client: TestClient, db_session: Session
):
    """The sub/superscript parentheses fold to a space rather than to ASCII
    parentheses, which are tsquery grouping operators. Folding to them raised
    "syntax error in tsquery" on input a user could actually type.

    Note the record is still found by its digits, not by the parentheses.
    """
    add_symbol_data(db_session)

    assert SCRIPT_SIGNS in search_uuids(client, "x⁽¹⁾")
    assert SCRIPT_SIGNS in search_uuids(client, "a₍₋₁₎")


def test_copyright_symbol(client: TestClient, db_session: Session):
    """Before this change unaccent rewrote the sign to "(C)", so a copyright
    search was really a search for the bare token "c"."""
    add_symbol_data(db_session)

    uuids = search_uuids(client, "©")
    assert COPYRIGHT in uuids
    assert FLAT not in uuids


def test_phonogram_symbol(client: TestClient, db_session: Session):
    add_symbol_data(db_session)

    assert PHONOGRAM in search_uuids(client, "℗")


def test_degree_symbol_in_coordinates(client: TestClient, db_session: Session):
    add_symbol_data(db_session)

    assert COORDINATES in search_uuids(client, "118°")


def test_coordinate_primes_separate_the_numbers(
    client: TestClient, db_session: Session
):
    """Stage 0: between digits the prime marks are punctuation, so 27 and 16
    stay separate tokens rather than fusing into 2716."""
    add_symbol_data(db_session)

    assert COORDINATES in search_uuids(client, "27 16")


def test_ampersand_control_unaffected(client: TestClient, db_session: Session):
    """Control: a record with no targeted characters must behave as before."""
    add_symbol_data(db_session)

    assert CONTROL in search_uuids(client, "Castles palaces")


def test_symbol_inside_phrase_search(client: TestClient, db_session: Session):
    """Exercises the "simple" phrase path. Catches the ordering bug: normalizing
    after format_query would emit malformed tsquery syntax here."""
    add_symbol_data(db_session)

    assert FLAT in search_uuids(client, '"D♭ major"')


def test_symbol_with_or_operator(client: TestClient, db_session: Session):
    add_symbol_data(db_session)

    uuids = search_uuids(client, "D♭ | F♯")
    assert FLAT in uuids
    assert SHARP in uuids


def test_bare_symbol_queries_do_not_error(client: TestClient, db_session: Session):
    """A symbol alone must not produce a 500 from malformed tsquery syntax."""
    add_symbol_data(db_session)

    for query in ["♭", "©", "°", "♭ ♯", "*♭", "℗", "♮"]:
        response = client.get("/search/", params={"q": query})
        assert response.status_code == 200, f"{query} returned {response.status_code}"


def test_wildcard_after_symbol_is_dropped(client: TestClient, db_session: Session):
    """Known limitation: sentinels are space padded, so the asterisk in "D♭*"
    becomes a standalone wildcard and format_query strips it. The search still
    succeeds, it just stops being a prefix match."""
    add_symbol_data(db_session)

    assert format_query(normalize_symbols("D♭*")) == "D & bcsymflat"
    assert FLAT in search_uuids(client, "D♭*")
