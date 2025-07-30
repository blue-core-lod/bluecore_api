from bluecore_api.app.routes.search import format_query
from bluecore_models.models import Work
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
    assert format_query("hello worl*") == "hello & worl:*"
    assert format_query("hello 1 world 2") == "hello & 1 & world & 2"
    assert format_query('"hello world" test') == "hello <-> world & test"
    assert format_query('" hello world " test') == "hello <-> world & test"
    assert (
        format_query('test "hello world" | "phrase search terms"')
        == "test & hello <-> world | phrase <-> search <-> terms"
    )


test_work_uuid = "370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
test_work_bluecore_uri = f"https://api.sinopia.io/resources/{test_work_uuid}"


def add_data(db_session: Session):
    jsonld_data = json.load(pathlib.Path("tests/blue-core-work.jsonld").open())

    db_session.add(
        Work(
            id=1,
            uuid=test_work_uuid,
            uri=test_work_bluecore_uri,
            data=jsonld_data,
        ),
    )


def test_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mit"})
    result = response.json()
    assert result["total"] == 1
    assert result["items"][0]["uri"].startswith(test_work_bluecore_uri)


def test_or_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mi | mit"})
    result = response.json()
    assert result["total"] == 1
    assert result["items"][0]["uri"].startswith(test_work_bluecore_uri)


def test_phrase_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": '"kumae chedo mit"'})
    result = response.json()
    assert result["total"] == 1
    assert result["items"][0]["uri"].startswith(test_work_bluecore_uri)


def test_wildcard_search(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mi*"})
    result = response.json()
    assert result["total"] == 1
    assert result["items"][0]["uri"].startswith(test_work_bluecore_uri)


def test_search_incomplete_word(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mi"})
    result = response.json()
    assert result["total"] == 0


def test_search_works(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get("/search/", params={"q": "kumae chedo mit", "type": "works"})
    result = response.json()
    assert result["total"] == 1
    assert result["items"][0]["uri"].startswith(test_work_bluecore_uri)


def test_search_instances(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get(
        "/search/", params={"q": "kumae chedo mit", "type": "instances"}
    )
    result = response.json()
    assert result["total"] == 0  # We didn't add any instances, so should return 0


def test_search_keyword_and_phrase(client: TestClient, db_session: Session):
    add_data(db_session)

    response = client.get(
        "/search/", params={"q": 'Chaesaeng "kumae chedo mit"', "type": "all"}
    )
    result = response.json()
    assert result["total"] == 1
    assert result["items"][0]["uri"].startswith(test_work_bluecore_uri)


if __name__ == "__main__":
    pytest.main()
