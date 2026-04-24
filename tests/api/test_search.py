from bluecore_api.app.routes.search import format_query
from bluecore_models.models import OtherResource, Work
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import json
import pathlib
import pytest


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
    work_data = json.load(pathlib.Path("tests/blue-core-work.jsonld").open())

    db_session.add(
        Work(
            id=1,
            uuid=test_work_uuid,
            uri=test_work_bluecore_uri,
            data=work_data,
        ),
    )


def add_other_resources(db_session: Session):
    eng = json.load(pathlib.Path("tests/blue-core-other-resources.json").open())
    kor = json.load(pathlib.Path("tests/blue-core-other-resources2.json").open())
    db_session.add(
        OtherResource(
            is_profile=True,
            uri="https://api.sinopia.io/profiles/test-profile",
            data=eng,
        ),
    )
    db_session.add(
        OtherResource(
            is_profile=True,
            uri="https://api.sinopia.io/profiles/test-profile2",
            data=kor,
        ),
    )
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
        == "https://bcld.info/api/search/?limit=10&offset=0&q=kumae+chedo+mit&type=all"
    )


def test_or_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mi | mit"})
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["uri"].startswith(test_work_bluecore_uri)
    assert result["total"] == 1
    assert result["links"]["first"] == (
        "https://bcld.info/api/search/?limit=10&offset=0&q=kumae+chedo+mi+%7C+mit&type=all"
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
        "https://bcld.info/api/search/?limit=10&offset=0&q=kumae+chedo+mi%2A&type=all"
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
        == "https://bcld.info/api/search/?limit=10&offset=0&q=kumae+chedo+mit&type=works"
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
    add_other_resources(db_session)

    response = client.get(
        "/search/profile", params={"q": "id.loc.gov/ontologies/bibframe/language"}
    )
    result = response.json()
    assert len(result["results"]) == 2
    assert result["results"][0]["uri"] == "https://api.sinopia.io/profiles/test-profile"
    assert result["total"] == 2
    assert (
        result["links"]["first"]
        == "https://bcld.info/api/search/profile/?limit=10&offset=0&q=id.loc.gov%2Fontologies%2Fbibframe%2Flanguage"
    )


def test_search_profile_limit(client: TestClient, db_session: Session):
    add_other_resources(db_session)

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
