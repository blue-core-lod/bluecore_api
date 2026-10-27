import json

import pytest
from bluecore_models.models import Profile
from bluecore_models.utils.graph import load_jsonld
from fastapi import HTTPException
from rdflib import RDF, Literal, Namespace, URIRef

from bluecore_api.app.utils.profile_versions import resolve_version_uri

SINOPIA = Namespace("http://sinopia.io/vocabulary/")


def test_create_profile(client):
    # An expanded JSON-LD Profile whose ResourceTemplate node carries a URI
    # minted on another server.
    old_uri = "https://dev.bcld.info/api/resources/1456282"
    document = [
        {
            "@id": old_uri,
            "@type": ["http://sinopia.io/vocabulary/ResourceTemplate"],
            "http://sinopia.io/vocabulary/hasResourceId": [
                {"@value": "bluecore:bf2:Agent:AgentOnly"}
            ],
        },
        {
            "@id": "http://id.loc.gov/ontologies/bibframe/Meeting",
            "http://www.w3.org/2000/01/rdf-schema#label": [{"@value": "Meeting"}],
        },
    ]

    response = client.post(
        "/profiles/",
        headers={"X-User": "cataloger"},
        json={"data": json.dumps(document)},
    )
    assert response.status_code == 201

    body = response.json()
    # Profiles are minted a uuid and a .../profiles/{uuid} uri, like Works.
    assert body["uuid"] is not None
    minted_uri = f"https://bcld.info/profiles/{body['uuid']}"
    assert body["uri"] == minted_uri

    # Stored as expanded JSON-LD (a list of nodes), the shape sinopia_editor
    # parses by hand -- not a compacted {"@context", "@graph"} object.
    assert isinstance(body["data"], list)

    # The ResourceTemplate type assertion now belongs to the minted URI, the URI
    # supplied in the request is gone, and the profile's properties came along.
    graph = load_jsonld(body["data"])
    assert (URIRef(minted_uri), RDF.type, SINOPIA.ResourceTemplate) in graph
    assert URIRef(old_uri) not in set(graph.subjects())
    assert graph.value(URIRef(minted_uri), SINOPIA.hasResourceId) == Literal(
        "bluecore:bf2:Agent:AgentOnly"
    )
    # Unrelated vocabulary nodes are left untouched.
    assert URIRef("http://id.loc.gov/ontologies/bibframe/Meeting") in set(
        graph.subjects()
    )


def test_create_profile_without_existing_template(client):
    """A Profile whose data carries no ResourceTemplate assertion still gets one
    minted for its URI."""
    document = [
        {
            "@id": "http://id.loc.gov/ontologies/bibframe/Meeting",
            "http://www.w3.org/2000/01/rdf-schema#label": [{"@value": "Meeting"}],
        }
    ]

    body = client.post(
        "/profiles/",
        headers={"X-User": "cataloger"},
        json={"data": json.dumps(document)},
    ).json()

    graph = load_jsonld(body["data"])
    assert (URIRef(body["uri"]), RDF.type, SINOPIA.ResourceTemplate) in graph


def test_read_profile_by_uuid(client):
    document = [
        {
            "@id": "https://example.com/profiles/one",
            "@type": ["http://sinopia.io/vocabulary/ResourceTemplate"],
            "http://www.w3.org/2000/01/rdf-schema#label": [{"@value": "Profile One"}],
        }
    ]
    created = client.post(
        "/profiles/",
        headers={"X-User": "cataloger"},
        json={"data": json.dumps(document)},
    ).json()

    response = client.get(f"/profiles/{created['uuid']}")
    assert response.status_code == 200
    body = response.json()
    assert body["uri"] == created["uri"]
    # The stored, re-homed ResourceTemplate round-trips through the GET.
    graph = load_jsonld(body["data"])
    assert (URIRef(created["uri"]), RDF.type, SINOPIA.ResourceTemplate) in graph


def test_read_profile_not_found(client):
    response = client.get("/profiles/00000000-0000-0000-0000-000000009999")
    assert response.status_code == 404


def test_update_profile(client, db_session):
    db_session.add(
        Profile(
            id=10,
            uuid="00000000-0000-0000-0000-000000000010",
            uri="https://bcld.info/profiles/00000000-0000-0000-0000-000000000010",
            data={"label": "before"},
        )
    )
    db_session.commit()

    response = client.put(
        "/profiles/00000000-0000-0000-0000-000000000010",
        headers={"X-User": "cataloger"},
        json={"data": json.dumps({"label": "after"})},
    )
    assert response.status_code == 200
    assert response.json()["data"] == {"label": "after"}


def test_list_profiles(client):
    for i in range(3):
        client.post(
            "/profiles/",
            headers={"X-User": "cataloger"},
            json={"data": json.dumps({"label": f"Profile {i}"})},
        )

    response = client.get("/profiles/")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["profiles"]) == 3
    assert "first" in body["links"]


def test_read_profile_by_uri(client):
    created = client.post(
        "/profiles/",
        headers={"X-User": "cataloger"},
        json={"data": json.dumps({"label": "By URI"})},
    ).json()

    response = client.get("/profiles/", params={"uri": created["uri"]})
    assert response.status_code == 200
    assert response.json()["uri"] == created["uri"]


def test_delete_profile(client):
    created = client.post(
        "/profiles/",
        headers={"X-User": "cataloger"},
        json={"data": json.dumps({"label": "To Be Deleted"})},
    ).json()
    profile_uuid = created["uuid"]

    response = client.delete(
        f"/profiles/{profile_uuid}", headers={"X-User": "cataloger"}
    )
    assert response.status_code == 204

    get_response = client.get(f"/profiles/{profile_uuid}")
    assert get_response.status_code == 404


def test_delete_profile_not_found(client):
    response = client.delete(
        "/profiles/00000000-0000-0000-0000-000000000000",
        headers={"X-User": "cataloger"},
    )
    assert response.status_code == 404


def test_delete_profile_forbidden(client, db_session):
    db_session.add(
        Profile(
            id=20,
            uuid="00000000-0000-0000-0000-000000000020",
            uri="https://bcld.info/profiles/00000000-0000-0000-0000-000000000020",
            data={"label": "forbidden test"},
        )
    )
    db_session.commit()

    response = client.delete("/profiles/00000000-0000-0000-0000-000000000020")
    assert response.status_code == 403


def test_profile_not_found_in_resources(client):
    """A Profile is not an OtherResource, so it is absent from /resources/."""
    created = client.post(
        "/profiles/",
        headers={"X-User": "cataloger"},
        json={"data": json.dumps({"label": "Not a resource"})},
    ).json()

    response = client.get(f"/resources/{created['id']}")
    assert response.status_code == 404


BCLD = "https://bcld.info"
CATALOGER = {"X-User": "cataloger"}


def post_profile(client, data: str = '{"label": "a profile"}') -> dict:
    response = client.post("/profiles/", headers=CATALOGER, json={"data": data})
    assert response.status_code == 201
    return response.json()


def newest_version_uri(client, profile: dict) -> str:
    versions = client.get(f"/profiles/{profile['uuid']}/versions").json()["versions"]
    return f"{profile['uri']}/version/{versions[-1]['id']}"


def test_create_profile_returns_its_version_uri(client):
    created = post_profile(client)

    assert created["version_uri"] == newest_version_uri(client, created)
    # it resolves, to what was just saved
    snapshot = client.get(created["version_uri"].removeprefix(BCLD))
    assert snapshot.status_code == 200
    assert snapshot.json()["data"] == created["data"]


def test_update_profile_returns_the_version_it_created(client):
    created = post_profile(client)

    response = client.put(
        f"/profiles/{created['uuid']}",
        headers=CATALOGER,
        json={"data": json.dumps({"label": "changed"})},
    )
    assert response.status_code == 200
    updated = response.json()

    assert updated["version_uri"] != created["version_uri"]
    assert updated["version_uri"] == newest_version_uri(client, created)


def test_profile_version_carries_its_own_uri(client):
    created = post_profile(client)
    client.put(
        f"/profiles/{created['uuid']}",
        headers=CATALOGER,
        json={"data": json.dumps({"label": "changed"})},
    )

    # the older version, not the newest
    snapshot = client.get(created["version_uri"].removeprefix(BCLD)).json()
    assert snapshot["version_uri"] == created["version_uri"]


def test_resolve_version_uri(client, db_session):
    created = post_profile(client)

    profile, version = resolve_version_uri(db_session, created["version_uri"])

    assert str(profile.uuid) == created["uuid"]
    assert created["version_uri"].endswith(f"/version/{version.id}")


def test_resolve_version_uri_unknown_version(client, db_session):
    created = post_profile(client)

    with pytest.raises(HTTPException) as error:
        resolve_version_uri(db_session, f"{created['uri']}/version/999999")
    assert error.value.status_code == 404


def test_resolve_version_uri_unknown_profile(client, db_session):
    with pytest.raises(HTTPException) as error:
        resolve_version_uri(
            db_session,
            f"{BCLD}/profiles/00000000-0000-0000-0000-000000009999/version/1",
        )
    assert error.value.status_code == 404


def test_resolve_version_uri_of_another_profiles_version(client, db_session):
    """versions.id is global, so another profile's version id must not resolve."""
    mine = post_profile(client)
    theirs = post_profile(client)
    their_version_id = theirs["version_uri"].rsplit("/", 1)[1]

    with pytest.raises(HTTPException) as error:
        resolve_version_uri(db_session, f"{mine['uri']}/version/{their_version_id}")
    assert error.value.status_code == 404


@pytest.mark.parametrize(
    "uri",
    [
        f"{BCLD}/profiles/00000000-0000-0000-0000-000000000001",
        f"{BCLD}/profiles/00000000-0000-0000-0000-000000000001/version/",
        f"{BCLD}/profiles/00000000-0000-0000-0000-000000000001/version/latest",
        "pcc:bf2:Title",
    ],
)
def test_resolve_version_uri_malformed(client, db_session, uri):
    with pytest.raises(HTTPException) as error:
        resolve_version_uri(db_session, uri)
    assert error.value.status_code == 422


def test_profile_by_uri_returns_its_version_uri(client):
    created = post_profile(client)

    found = client.get("/profiles/", params={"uri": created["uri"]}).json()
    assert found["version_uri"] == created["version_uri"]


def test_profile_search_returns_version_uris(client):
    created = post_profile(client)

    results = client.get("/search/profile").json()["results"]
    assert [r["version_uri"] for r in results] == [created["version_uri"]]
