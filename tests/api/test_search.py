import json
import pathlib

import pytest
from bluecore_models.models import Hub, Instance, Profile, Work
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bluecore_api.app.routes.search import format_query


def test_format_query():
    assert format_query("") == ""
    assert format_query("hello world") == "hello & world"
    assert format_query(" hello world") == "hello & world"
    assert format_query("hello  world") == "hello & world"
    assert format_query("hello | world") == "hello | world"
    assert format_query("hello|world") == "hello | world"
    assert format_query("hello |world test") == "hello | world & test"
    assert format_query("hello 1 world 2") == "hello & 1 & world & 2"
    assert format_query('"hello world" test') == "hello <-> world & test"
    assert format_query('" hello world " test') == "hello <-> world & test"
    assert (
        format_query('test "hello world" | "phrase search terms"')
        == "test & hello <-> world | phrase <-> search <-> terms"
    )
    assert (
        format_query("bluecore:bf2:Monograph:Work")
        == "bluecore & bf2 & Monograph & Work"
    )
    assert (
        format_query('"Ocean Becoming : Pacific pavements"')
        == "Ocean <-> Becoming <-> \\: <-> Pacific <-> pavements"
    )
    assert (
        format_query('"phrase with ampersand & test"')
        == "phrase <-> with <-> ampersand <-> \\& <-> test"
    )
    assert (
        format_query('"phrase with ampersand&test2"')
        == "phrase <-> with <-> ampersand\\&test2"
    )
    assert (
        format_query('"phrase with ampersand& test3"')
        == "phrase <-> with <-> ampersand\\& <-> test3"
    )
    assert (
        format_query('"phrase with ampersand &test4"')
        == "phrase <-> with <-> ampersand <-> \\&test4"
    )
    assert (
        format_query('"phrase with double ampersand && test"')
        == "phrase <-> with <-> double <-> ampersand <-> \\&\\& <-> test"
    )
    assert (
        format_query('"phrase with | or operator test"')
        == "phrase <-> with <-> \\| <-> or <-> operator <-> test"
    )
    assert (
        format_query('"phrase with|or operator test2"')
        == "phrase <-> with\\|or <-> operator <-> test2"
    )
    assert (
        format_query('"phrase with| or operator test3"')
        == "phrase <-> with\\| <-> or <-> operator <-> test3"
    )
    assert (
        format_query('"phrase with |or operator test4"')
        == "phrase <-> with <-> \\|or <-> operator <-> test4"
    )
    assert format_query("hello worl*") == "hello & worl:*"
    assert format_query("*leading wildcard test") == "leading & wildcard & test"
    assert format_query('"hell* worl*"') == "hell:* <-> worl:*"
    assert format_query('"inval * wildcard *"') == "inval <-> wildcard"
    assert format_query('"inval*wildcard test2"') == "inval:* <-> wildcard <-> test2"
    assert format_query('"inval *wildcard test3"') == "inval <-> wildcard <-> test3"
    assert (
        format_query('"*phrase leading wildcard test"')
        == "phrase <-> leading <-> wildcard <-> test"
    )
    assert (
        format_query('"double wild card** test"')
        == "double <-> wild <-> card:* <-> test"
    )
    assert (
        format_query('"double wild card* * test2"')
        == "double <-> wild <-> card:* <-> test2"
    )
    assert (
        format_query('"double wild card* *test3"')
        == "double <-> wild <-> card:* <-> test3"
    )
    assert format_query("http://uri.org/test") == "http\\://uri.org/test"
    assert format_query("colon : test2") == "colon & test2"
    assert format_query("colon: test3") == "colon & test3"
    assert format_query("colon :test4") == "colon & test4"
    assert (
        format_query('"phrase colon escape : test"')
        == "phrase <-> colon <-> escape <-> \\: <-> test"
    )
    assert (
        format_query('"phrase colon escape:test2"')
        == "phrase <-> colon <-> escape\\:test2"
    )
    assert (
        format_query('"phrase colon escape: test3"')
        == "phrase <-> colon <-> escape\\: <-> test3"
    )
    assert (
        format_query('"phrase colon escape :test4"')
        == "phrase <-> colon <-> escape <-> \\:test4"
    )
    assert (
        format_query("trailing and operator test &")
        == "trailing & and & operator & test"
    )
    assert (
        format_query("trailing or operator test|") == "trailing & or & operator & test"
    )


test_work_uuid = "370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
test_work_bluecore_uri = f"https://api.sinopia.io/resources/{test_work_uuid}"


def add_data(db_session: Session):
    with pathlib.Path("tests/blue-core-work.jsonld").open() as fo:
        work_data = json.load(fo)

    db_session.add(
        Work(
            id=1,
            uuid=test_work_uuid,
            uri=test_work_bluecore_uri,
            data=work_data,
        ),
    )


test_hub_uuid = "62a26d82-4e65-c696-afed-b12d215a35b1"
test_hub_uri = f"https://bcld.info/hubs/{test_hub_uuid}"
# A title sharing a distinctive word with the Work fixture, so one "all" search
# turns up both and the results have to be grouped by kind.
test_hub_title = "Chaesaeng enŏji kumae sirijŭ"


def add_hub(db_session: Session):
    db_session.add(
        Hub(
            id=2,
            uuid=test_hub_uuid,
            uri=test_hub_uri,
            data={
                "@id": test_hub_uri,
                "@type": ["Work", "Hub"],
                "title": {"@type": "Title", "mainTitle": test_hub_title},
            },
        ),
    )
    db_session.commit()


def add_profiles(db_session: Session):
    with pathlib.Path("tests/blue-core-other-resources.json").open() as fo:
        eng = json.load(fo)
    with pathlib.Path("tests/blue-core-other-resources2.json").open() as fo:
        kor = json.load(fo)
    db_session.add(
        Profile(
            uri="https://api.sinopia.io/profiles/test-profile",
            data=eng,
        ),
    )
    db_session.add(
        Profile(
            uri="https://api.sinopia.io/profiles/test-profile2",
            data=kor,
        ),
    )
    db_session.commit()


def add_scoped_search_data(db_session: Session):
    """Add title values plus a non-title value that scoped tests can tell apart."""
    db_session.add(
        Work(
            id=70,
            uuid="00000000-0000-0000-0000-000000000070",
            uri="https://bcld.info/works/00000000-0000-0000-0000-000000000070",
            data={
                "@id": "https://bcld.info/works/00000000-0000-0000-0000-000000000070",
                "@type": "Work",
                "title": [
                    {
                        "@type": "Title",
                        "mainTitle": "primaryscope",
                        "subtitle": "subtitlescope",
                    },
                    {"@type": "VariantTitle", "mainTitle": "variantscope"},
                    {"@type": "ParallelTitle", "mainTitle": "parallelscope"},
                ],
                "note": {"label": "notescope"},
            },
        )
    )
    db_session.commit()


def add_each_searchable_resource_type(db_session: Session):
    """Add a Work, Instance, and Hub that share one title search term."""
    models = (Work, Instance, Hub)
    names = ("works", "instances", "hubs")
    resources = []
    for id_, (model, name) in enumerate(zip(models, names, strict=True), start=71):
        uri = f"https://bcld.info/{name}/00000000-0000-0000-0000-0000000000{id_}"
        resources.append(
            model(
                id=id_,
                uuid=f"00000000-0000-0000-0000-0000000000{id_}",
                uri=uri,
                data={
                    "@id": uri,
                    "@type": model.__name__,
                    "title": {"@type": "Title", "mainTitle": "alltypestitle"},
                },
            )
        )
    db_session.add_all(resources)
    db_session.commit()


def test_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mit"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1
    assert (
        result["links"]["first"]
        == "https://bcld.info/api/search/?limit=20&offset=0&q=kumae+chedo+mit&type=all"
    )


@pytest.mark.parametrize(
    "query",
    [
        "primaryscope",
        "variantscope",
        "parallelscope",
        "subtitlescope",
    ],
)
def test_title_scope_searches_supported_title_values(
    client: TestClient, db_session: Session, query: str
):
    add_scoped_search_data(db_session)

    response = client.get("/search/", params={"q": query, "scope": "title"})
    result = response.json()

    assert response.status_code == 200
    assert result["total"] == 1
    assert result["results"][0]["type"] == "works"
    assert result["links"]["first"].endswith(f"&q={query}&type=all&scope=title")


def test_title_scope_searches_expanded_jsonld(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get(
        "/search/", params={"q": "Renewable energy policy", "scope": "title"}
    )
    result = response.json()

    assert response.status_code == 200
    assert result["total"] == 1
    assert result["results"][0]["uri"] == test_work_bluecore_uri


def test_title_scope_excludes_non_title_values(client: TestClient, db_session: Session):
    add_scoped_search_data(db_session)

    scoped = client.get("/search/", params={"q": "notescope", "scope": "title"}).json()
    unscoped = client.get("/search/", params={"q": "notescope"}).json()

    assert scoped["total"] == 0
    assert unscoped["total"] == 1


def test_title_scope_includes_all_resource_types(
    client: TestClient, db_session: Session
):
    add_each_searchable_resource_type(db_session)

    result = client.get(
        "/search/", params={"q": "alltypestitle", "scope": "title"}
    ).json()

    assert result["total"] == 3
    assert {resource["type"] for resource in result["results"]} == {
        "works",
        "instances",
        "hubs",
    }


def test_search_html_can_scope_to_titles(client: TestClient, db_session: Session):
    add_scoped_search_data(db_session)

    response = client.get("/search", params={"q": "variantscope", "scope": "title"})

    assert response.status_code == 200
    assert "1 result" in response.text
    assert '<select name="scope" aria-label="Search scope">' in response.text
    assert '<option value="title" selected>' in response.text


def test_search_rejects_unknown_scope(client: TestClient):
    response = client.get("/search/", params={"q": "anything", "scope": "isbn"})

    assert response.status_code == 422


def test_search_html(client: TestClient, db_session: Session):
    add_data(db_session)

    # The public, human-facing search (GET /search, distinct from JSON /search/).
    response = client.get("/search", params={"q": "kumae chedo mit"})
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert "Search results" in response.text
    # The single matching Work is grouped and linked to its dereferenceable URL.
    assert "1 result" in response.text
    assert test_work_bluecore_uri in response.text


def test_or_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mi | mit"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1
    assert result["links"]["first"] == (
        "https://bcld.info/api/search/?limit=20&offset=0&q=kumae+chedo+mi+%7C+mit&type=all"
    )


def test_phrase_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": '"kumae chedo mit"'})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1


def test_wildcard_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mi*"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1
    assert result["links"]["first"] == (
        "https://bcld.info/api/search/?limit=20&offset=0&q=kumae+chedo+mi%2A&type=all"
    )


def test_search_incomplete_word(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mi"})
    result = response.json()
    assert len(result["results"]) == 0
    assert result["total"] == 0


def test_search_works(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mit", "type": "works"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1
    assert (
        result["links"]["first"]
        == "https://bcld.info/api/search/?limit=20&offset=0&q=kumae+chedo+mit&type=works"
    )


def test_search_instances(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get(
        "/search/", params={"q": "kumae chedo mit", "type": "instances"}
    )
    result = response.json()
    assert (
        len(result["results"]) == 0
    )  # We didn't add any instances, so should return 0
    assert result["total"] == 0


def test_search_hubs(client: TestClient, db_session: Session):
    add_data(db_session)
    add_hub(db_session)

    response = client.get("/search/", params={"q": "sirijŭ", "type": "hubs"})
    result = response.json()

    assert result["total"] == 1
    assert result["results"][0]["uri"] == test_hub_uri
    assert result["results"][0]["type"] == "hubs"
    assert (
        result["links"]["first"]
        == "https://bcld.info/api/search/?limit=20&offset=0&q=sirij%C5%AD&type=hubs"
    )


def test_search_all_includes_hubs(client: TestClient, db_session: Session):
    """A Hub used to be invisible to the default search; "all" now covers it."""
    add_data(db_session)
    add_hub(db_session)

    response = client.get("/search/", params={"q": "kumae"})
    result = response.json()

    assert result["total"] == 2
    assert {r["uri"] for r in result["results"]} == {
        test_work_bluecore_uri,
        test_hub_uri,
    }


def test_search_html_groups_hubs_separately(client: TestClient, db_session: Session):
    add_data(db_session)
    add_hub(db_session)

    response = client.get("/search", params={"q": "kumae"})

    assert response.status_code == 200
    page = response.text
    assert "2 results" in page
    # each kind under its own heading, Works before Hubs
    assert page.index(">Works<") < page.index(">Hubs<")
    assert f'href="{test_work_bluecore_uri}"' in page
    assert f'href="{test_hub_uri}"' in page


def test_search_html_hubs_only_still_gets_a_heading(
    client: TestClient, db_session: Session
):
    add_data(db_session)
    add_hub(db_session)

    response = client.get("/search", params={"q": "kumae", "type": "hubs"})

    assert response.status_code == 200
    page = response.text
    assert "1 result" in page
    assert ">Hubs<" in page
    assert f'href="{test_work_bluecore_uri}"' not in page


def test_search_keyword_and_phrase(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get(
        "/search/", params={"q": 'Chaesaeng "kumae chedo mit"', "type": "all"}
    )
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1


def test_search_diacritics(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "Chaesaeng enŏji", "type": "all"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1


def test_uri(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get(
        "/search/", params={"q": test_work_bluecore_uri, "type": "all"}
    )
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1


def test_bad_query_trailing_operator(client: TestClient, db_session: Session):
    add_data(db_session)

    # trailing | operator is ignored
    response = client.get("/search/", params={"q": "kumae chedo mit |"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["total"] == 1


def test_bad_query_colon_in_phrase(client: TestClient, db_session: Session):
    add_data(db_session)

    # kumae <-> \: <-> chedo <-> mit doesn't match because of the escaped colon
    response = client.get("/search/", params={"q": '"kumae : chedo mit"'})
    result = response.json()
    assert len(result["results"]) == 0
    assert result["total"] == 0


def test_search_profile_no_match(client: TestClient, db_session: Session):
    response = client.get("/search/profile", params={})
    result = response.json()
    assert len(result["results"]) == 0  # No profiles added, should return 0
    assert result["total"] == 0


def test_search_profile(client: TestClient, db_session: Session):
    add_profiles(db_session)

    response = client.get(
        "/search/profile", params={"q": "id.loc.gov/ontologies/bibframe/language"}
    )
    result = response.json()
    assert len(result["results"]) == 2
    assert result["results"][0]["uri"] == "https://api.sinopia.io/profiles/test-profile"
    assert result["total"] == 2
    assert (
        result["links"]["first"]
        == "https://bcld.info/api/search/profile/?limit=20&offset=0&q=id.loc.gov%2Fontologies%2Fbibframe%2Flanguage"
    )


def test_search_profile_limit(client: TestClient, db_session: Session):
    add_profiles(db_session)

    response = client.get(
        "/search/profile",
        params={"q": "id.loc.gov/ontologies/bibframe/language", "limit": 1},
    )
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"] == "https://api.sinopia.io/profiles/test-profile"
    assert result["total"] == 2


if __name__ == "__main__":
    pytest.main()
