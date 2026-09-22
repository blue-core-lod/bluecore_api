"""GET /search/federated -- the grouped envelope.

Stage 1 covers the Blue Core source only, so these tests establish the shape
and, most importantly, that GET /search/ is untouched by any of it.
"""

import pytest
from bluecore_models.models import Hub, Instance, Work
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

TITLE = "federatedtesttitle"


@pytest.fixture
def searchable(db_session: Session) -> None:
    """One Work, Instance and Hub sharing a title no other fixture uses."""
    models = (Work, Instance, Hub)
    names = ("works", "instances", "hubs")
    for id_, (model, name) in enumerate(zip(models, names, strict=True), start=91):
        uri = f"https://bcld.info/{name}/00000000-0000-0000-0000-0000000000{id_}"
        db_session.add(
            model(
                id=id_,
                uuid=f"00000000-0000-0000-0000-0000000000{id_}",
                uri=uri,
                data={
                    "@id": uri,
                    "@type": model.__name__,
                    "title": {"@type": "Title", "mainTitle": TITLE},
                },
            )
        )
    db_session.commit()


def _group(payload: dict, source_id: str) -> dict:
    return next(g for g in payload["sources"] if g["id"] == source_id)


def test_results_are_grouped_by_source(client: TestClient, searchable: None):
    payload = client.get("/search/federated", params={"q": TITLE}).json()

    assert [g["id"] for g in payload["sources"]] == ["bluecore"]
    group = _group(payload, "bluecore")
    assert group["status"] == "ok"
    assert group["error"] is None
    assert group["total"] == 3
    assert group["total_is_exact"] is True
    assert len(group["results"]) == 3
    assert payload["partial"] is False


def test_local_results_are_labelled_as_ours(client: TestClient, searchable: None):
    payload = client.get("/search/federated", params={"q": TITLE}).json()

    for result in _group(payload, "bluecore")["results"]:
        assert result["source"] == "bluecore"
        assert result["source_label"] == "Blue Core"
        # A Blue Core record is trivially already in Blue Core; clients should
        # not have to special-case which sources can fill this in.
        assert result["local_uri"] == result["uri"]
        assert result["id"] is not None
        assert result["data"]["@context"].endswith("/context.jsonld")


def test_explicit_nulls_are_kept(client: TestClient, searchable: None):
    """Unlike the rest of the API this endpoint does not drop None.

    "we looked and there is no copy" and "we did not look" have to be
    distinguishable, and an absent key cannot say either.
    """
    payload = client.get("/search/federated", params={"q": TITLE}).json()

    result = _group(payload, "bluecore")["results"][0]
    assert "proxy_uri" in result and result["proxy_uri"] is None
    assert "rank" in result and result["rank"] is None
    assert "error" in _group(payload, "bluecore")


def test_type_filter_is_honored(client: TestClient, searchable: None):
    payload = client.get(
        "/search/federated", params={"q": TITLE, "type": "works"}
    ).json()

    group = _group(payload, "bluecore")
    assert group["total"] == 1
    assert group["results"][0]["type"] == "works"


def test_paging_links_are_per_source(client: TestClient, searchable: None):
    payload = client.get(
        "/search/federated", params={"q": TITLE, "limit": 2, "offset": 2}
    ).json()

    links = _group(payload, "bluecore")["links"]
    base = "https://bcld.info/api/search/federated"
    assert links["first"] == f"{base}?limit=2&offset=0&q={TITLE}&type=all"
    assert links["prev"] == f"{base}?limit=2&offset=0&q={TITLE}&type=all"
    # A short final page means there is nothing after it.
    assert links["next"] is None


def test_unknown_source_is_rejected(client: TestClient):
    response = client.get("/search/federated", params={"q": TITLE, "sources": "nope"})

    assert response.status_code == 422
    assert "Unknown source" in response.json()["detail"]


def test_sources_parameter_narrows(client: TestClient, searchable: None):
    payload = client.get(
        "/search/federated", params={"q": TITLE, "sources": "bluecore"}
    ).json()

    assert [g["id"] for g in payload["sources"]] == ["bluecore"]


def test_plain_search_endpoint_is_unchanged(client: TestClient, searchable: None):
    """Regression guard. GET /search/ is what sinopia_editor calls today and
    what the MCP `search` tool exposes; federated search must not touch it."""
    payload = client.get("/search/", params={"q": TITLE}).json()

    assert sorted(payload) == ["links", "results", "total"]
    assert payload["total"] == 3
    assert sorted(payload["results"][0]) == [
        "created_at",
        "data",
        "id",
        "type",
        "updated_at",
        "uri",
        "uuid",
    ]
    assert (
        payload["links"]["first"]
        == f"https://bcld.info/api/search/?limit=20&offset=0&q={TITLE}&type=all"
    )
