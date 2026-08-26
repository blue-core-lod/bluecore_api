"""Verification for the title scope: that it uses its index, and that the
title_vector generated column indexes the title shapes our records actually use.

tests/api/test_search.py covers what the scope returns. This covers the two
things that are easy to break silently underneath it -- the query stops hitting
the GIN index, or a title shape stops reaching the vector at all -- plus the
query syntax edge cases a reader can type into the search box.

Run just these with:

    uv run pytest tests/api/test_search_title_index.py
"""

import pytest
from bluecore_models.models import Work
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

TITLE_INDEX = "index_resource_base_on_title_vector"


def _work(db_session: Session, id_: int, title) -> str:
    uri = f"https://bcld.info/works/00000000-0000-0000-0000-0000000001{id_:02d}"
    db_session.add(
        Work(
            id=900 + id_,
            uuid=f"00000000-0000-0000-0000-0000000001{id_:02d}",
            uri=uri,
            data={"@id": uri, "@type": "Work", "title": title},
        )
    )
    db_session.commit()
    return uri


def _uris(client: TestClient, q: str, scope: str = "title") -> list[str]:
    response = client.get("/search/", params={"q": q, "scope": scope})
    assert response.status_code == 200, f"{q!r} returned {response.status_code}"
    return [r["uri"] for r in response.json()["results"]]


# --- the index is actually used ---------------------------------------------


def test_title_scope_reads_the_gin_index(client: TestClient, db_session: Session):
    """A title search must not degrade into a sequential scan.

    The route writes the operands as `tsquery @@ tsvector`, the reverse of the
    usual order; this asserts the planner still commutes it onto the index. A
    small test table makes a sequential scan look cheap, so seqscan is disabled
    to ask whether the index *can* serve the query at all -- which is the thing
    that breaks when the column, the index or the operator drift apart.
    """
    # LOCAL, so it lasts only as long as this test's transaction.
    db_session.execute(text("set local enable_seqscan = off"))
    plan = "\n".join(
        row[0]
        for row in db_session.execute(
            text(
                "explain select id from resource_base "
                "where to_tsquery('english', unaccent('gene')) @@ title_vector"
            )
        )
    )
    assert TITLE_INDEX in plan, plan
    assert "Seq Scan" not in plan, plan


# --- every title shape reaches the vector ------------------------------------


def test_a_title_object_is_indexed(client: TestClient, db_session: Session):
    uri = _work(db_session, 1, {"@type": "Title", "mainTitle": "harpsichord"})
    assert _uris(client, "harpsichord") == [uri]


def test_a_subtitle_is_indexed(client: TestClient, db_session: Session):
    uri = _work(db_session, 2, {"mainTitle": "collected", "subtitle": "clavichordia"})
    assert _uris(client, "clavichordia") == [uri]


def test_every_title_in_a_list_is_indexed(client: TestClient, db_session: Session):
    """Variant and parallel titles sit beside the title proper in a list, and a
    reader searching a variant should still find the record."""
    uri = _work(
        db_session,
        3,
        [
            {"@type": "Title", "mainTitle": "primarylute"},
            {"@type": "VariantTitle", "mainTitle": "variantlute"},
            {"@type": "ParallelTitle", "mainTitle": "parallellute"},
        ],
    )
    for query in ("primarylute", "variantlute", "parallellute"):
        assert _uris(client, query) == [uri], query


def test_a_record_with_no_title_is_not_reachable(
    client: TestClient, db_session: Session
):
    """An empty title_vector matches nothing, rather than matching everything."""
    _work(db_session, 4, {"@type": "Title"})
    assert _uris(client, "anything") == []


def test_a_symbol_survives_into_the_index(client: TestClient, db_session: Session):
    """normalize_symbols runs on the query, bluecore_normalize on the column, and
    the two have to agree or symbol search works everywhere except here."""
    uri = _work(db_session, 5, {"mainTitle": "Sonata in D♭ minor"})
    assert _uris(client, "D♭") == [uri]


def test_the_index_is_accent_insensitive(client: TestClient, db_session: Session):
    uri = _work(db_session, 6, {"mainTitle": "Jeux vidéoscope"})
    assert _uris(client, "videoscope") == [uri]
    assert _uris(client, "vidéoscope") == [uri]


def test_non_latin_titles_are_indexed(client: TestClient, db_session: Session):
    uri = _work(db_session, 7, {"mainTitle": "岡部隆志"})
    assert _uris(client, "岡部隆志") == [uri]


# --- the scope actually narrows ----------------------------------------------


def test_the_scope_ignores_text_outside_the_title(
    client: TestClient, db_session: Session
):
    """The whole point of the scope: a term only in a note must not match."""
    uri = "https://bcld.info/works/00000000-0000-0000-0000-000000000199"
    db_session.add(
        Work(
            id=999,
            uuid="00000000-0000-0000-0000-000000000199",
            uri=uri,
            data={
                "@id": uri,
                "@type": "Work",
                "title": {"mainTitle": "titledword"},
                "note": {"label": "notedword"},
            },
        )
    )
    db_session.commit()

    assert _uris(client, "notedword") == []
    assert _uris(client, "notedword", scope="all") == [uri]
    assert _uris(client, "titledword") == [uri]


def test_the_scope_ignores_vocabulary_values(client: TestClient, db_session: Session):
    """Subjects, genre forms, contributors and the rest belong to the record, not
    to its title. A title search that answered with them would be answering a
    question the reader did not ask."""
    uri = "https://bcld.info/works/00000000-0000-0000-0000-000000000198"
    db_session.add(
        Work(
            id=998,
            uuid="00000000-0000-0000-0000-000000000198",
            uri=uri,
            data={
                "@id": uri,
                "@type": "Work",
                "title": {"mainTitle": "titledword"},
                "subject": {
                    "@id": "http://id.loc.gov/authorities/subjects/sh1",
                    "rdfs:label": "subjectword",
                },
                "genreForm": {"rdfs:label": "genreword"},
                "contribution": {
                    "@type": "Contribution",
                    "agent": {"rdfs:label": "agentword"},
                    "role": {"code": "roleword"},
                },
                "classification": {"classificationPortion": "classword"},
                "language": {"rdfs:label": "languageword"},
            },
        )
    )
    db_session.commit()

    assert _uris(client, "titledword") == [uri]
    for term in (
        "subjectword",
        "genreword",
        "agentword",
        "roleword",
        "classword",
        "languageword",
    ):
        assert _uris(client, term) == [], f"{term} reachable under scope=title"
        assert _uris(client, term, scope="all") == [uri], f"{term} lost from scope=all"


# --- query syntax a reader can type ------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "symphonium",
        "symphonium major",
        "banana | symphonium",
        "symph*",
        '"symphonium in d"',
    ],
)
def test_supported_query_forms_find_the_record(
    client: TestClient, db_session: Session, query: str
):
    uri = _work(db_session, 8, {"mainTitle": "Symphonium in D major"})
    assert _uris(client, query) == [uri], query


@pytest.mark.parametrize("query", ["", "*", "  "])
def test_an_empty_query_is_not_an_error(
    client: TestClient, db_session: Session, query: str
):
    """No search text means browse, not a 400 and not a crash."""
    _work(db_session, 9, {"mainTitle": "anything"})
    assert (
        client.get("/search/", params={"q": query, "scope": "title"}).status_code == 200
    )


# A query carrying a bare tsquery operator -- "fish & chips", "a ! b", "a <-> b"
# -- reaches to_tsquery as malformed syntax and 500s, and a quoted phrase holding
# one silently matches nothing. Both are in format_query, both predate the title
# scope and affect every scope, so they are tracked as their own issue rather
# than pinned here. See https://github.com/blue-core-lod/bluecore_api/issues/300.
