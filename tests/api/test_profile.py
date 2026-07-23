import json

from bluecore_models.models import Profile
from bluecore_models.utils.graph import load_jsonld
from rdflib import RDF, Literal, Namespace, URIRef

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
