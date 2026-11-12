import json

import pytest
from bluecore_models.models import (
    Hub,
    Instance,
    Profile,
    ResourceBase,
    Version,
    Work,
)
from bluecore_models.utils.graph import load_jsonld
from fastapi import HTTPException
from rdflib import RDF, Literal, Namespace, URIRef
from sinopia_templates import BF, Prop, template
from sqlalchemy import update

from bluecore_api.app.utils import template_compat
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


def test_list_profiles_returns_version_uris(client):
    created = post_profile(client)

    listed = client.get("/profiles/").json()["profiles"]

    assert listed[0]["version_uri"] == created["version_uri"]
    assert "title_vector" not in listed[0]


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
        f"{BCLD}/profiles/00000000-0000-0000-0000-000000000001/version/1/version/2",
        "urn:anything/version/1",
        f"{BCLD}/works/00000000-0000-0000-0000-000000000001/version/1",
    ],
)
def test_resolve_version_uri_rejects_non_profile_uris(db_session, uri):
    with pytest.raises(HTTPException) as error:
        resolve_version_uri(db_session, uri)
    assert error.value.status_code == 422


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


HAS_RESOURCE_TEMPLATE = "http://sinopia.io/vocabulary/hasResourceTemplate"


def nesting(*refs: str) -> str:
    """A profile whose property templates nest the given profile references."""
    return json.dumps(
        [
            {
                "@id": f"_:attributes{i}",
                "@type": ["http://sinopia.io/vocabulary/ResourcePropertyTemplate"],
                "http://sinopia.io/vocabulary/hasResourceTemplateId": [{"@id": ref}],
            }
            for i, ref in enumerate(refs)
        ]
    )


def add_record(
    db_session, model, name: str, template: str, properties: dict | None = None
):
    """A Work or Instance made with the given template, framed as stored.

    properties are expanded JSON-LD (full predicate IRIs) added to the record.
    """
    uri = f"{BCLD}/{model.__tablename__}/{name}"
    db_session.add(
        model(
            uri=uri,
            data={
                "@id": uri,
                "@type": [model.__name__],
                HAS_RESOURCE_TEMPLATE: [{"@id": template}],
                **(properties or {}),
            },
        )
    )
    db_session.commit()
    return uri


def validate(client, profile: dict, **kwargs):
    return client.post(
        f"/profiles/{profile['uuid']}/validate", headers=CATALOGER, **kwargs
    )


def test_delete_profile_used_by_a_record(client, db_session):
    profile = post_profile(client)
    record = add_record(db_session, Work, "w1", profile["version_uri"])

    response = client.delete(f"/profiles/{profile['uuid']}", headers=CATALOGER)

    assert response.status_code == 409
    assert record in response.json()["detail"]
    assert client.get(f"/profiles/{profile['uuid']}").status_code == 200


def test_delete_profile_nested_by_version(client):
    title = post_profile(client)
    work = post_profile(client, nesting(title["version_uri"]))

    response = client.delete(f"/profiles/{title['uuid']}", headers=CATALOGER)

    assert response.status_code == 409
    assert work["uri"] in response.json()["detail"]


def test_delete_profile_nested_by_plain_uri(client):
    title = post_profile(client)
    post_profile(client, nesting(title["uri"]))

    response = client.delete(f"/profiles/{title['uuid']}", headers=CATALOGER)

    assert response.status_code == 409


def test_delete_profile_nested_by_a_pinned_parent_version(client, db_session):
    """A record pinned to an old parent version still needs the nested profile."""
    title = post_profile(client)
    work = post_profile(client, nesting(title["version_uri"]))
    record = add_record(db_session, Work, "w1", work["version_uri"])
    client.put(
        f"/profiles/{work['uuid']}",
        headers=CATALOGER,
        json={"data": json.dumps({"label": "no longer nests title"})},
    )

    response = client.delete(f"/profiles/{title['uuid']}", headers=CATALOGER)

    assert response.status_code == 409, f"{record} would point at a dangling template"
    assert work["uri"] in response.json()["detail"]


def test_delete_profile_whose_uri_another_extends(client, db_session):
    """A profile URI that merely starts with this one's is not a reference."""
    profile = post_profile(client)
    add_record(db_session, Work, "w1", f"{profile['uri']}-copy")

    response = client.delete(f"/profiles/{profile['uuid']}", headers=CATALOGER)

    assert response.status_code == 204


def test_validate_unknown_profile(client):
    response = client.post(
        "/profiles/00000000-0000-0000-0000-000000009999/validate", headers=CATALOGER
    )
    assert response.status_code == 404


@pytest.mark.parametrize("data", ["not json", "42", '{"@context": 5}'])
def test_validate_data_that_is_not_jsonld(client, data):
    profile = post_profile(client)

    response = validate(client, profile, json={"data": data})

    assert response.status_code == 422


def test_validate_never_writes(client, db_session):
    profile = post_profile(client)
    versions_before = db_session.query(Version).count()

    response = validate(client, profile, json={"data": json.dumps(template(WORK))})

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(Version).count() == versions_before
    stored = client.get(f"/profiles/{profile['uuid']}").json()
    assert stored["data"] == profile["data"]


def test_validate_an_unused_profile(client):
    profile = post_profile(client)

    body = validate(client, profile).json()

    assert body == {
        "profile_uuid": profile["uuid"],
        "profile_uri": profile["uri"],
        "current_version_uri": profile["version_uri"],
        "instance_count": 0,
        "versions": [],
        "instances": [],
        "requires_new_version": False,
        "changes": [],
        "incompatible_instances": [],
        "unchecked_instances": [],
        "unresolved_templates": [],
        "resource_version_uri": None,
        "is_latest": None,
        "compatible": None,
    }


def test_validate_a_top_level_profile(client, db_session):
    profile = post_profile(client)
    old_version = profile["version_uri"]
    w1 = add_record(db_session, Work, "w1", old_version)
    i1 = add_record(db_session, Instance, "i1", profile["uri"])
    new_version = client.put(
        f"/profiles/{profile['uuid']}",
        headers=CATALOGER,
        json={"data": json.dumps({"label": "changed"})},
    ).json()["version_uri"]
    i2 = add_record(db_session, Instance, "i2", new_version)
    # made with some other profile
    add_record(db_session, Work, "w2", post_profile(client)["version_uri"])

    body = validate(client, profile).json()

    assert body["current_version_uri"] == new_version
    assert body["instance_count"] == 3
    assert sorted(body["versions"], key=lambda v: v["version_uri"] or "") == sorted(
        [
            {"version_uri": None, "instance_count": 1},
            {"version_uri": old_version, "instance_count": 1},
            {"version_uri": new_version, "instance_count": 1},
        ],
        key=lambda v: v["version_uri"] or "",
    )
    assert {i["uri"]: i["version_uri"] for i in body["instances"]} == {
        w1: old_version,
        i1: None,
        i2: new_version,
    }


def test_validate_a_nested_profile(client, db_session):
    """Records name only their root template, so a nested profile's records are
    those made with any template that nests it, however deeply."""
    title = post_profile(client)
    work = post_profile(client, nesting(title["uri"]))
    monograph = post_profile(client, nesting(work["uri"]))
    w1 = add_record(db_session, Work, "w1", work["version_uri"])
    i1 = add_record(db_session, Instance, "i1", monograph["version_uri"])

    body = validate(client, title).json()

    assert body["instance_count"] == 2
    assert {i["uri"]: i["version_uri"] for i in body["instances"]} == {
        w1: work["version_uri"],
        i1: monograph["version_uri"],
    }


def test_validate_pages_instances(client, db_session):
    profile = post_profile(client)
    for n in range(3):
        add_record(db_session, Instance, f"i{n}", profile["version_uri"])

    body = validate(client, profile, params={"limit": 2, "offset": 2}).json()

    assert body["instance_count"] == 3
    assert [i["uri"] for i in body["instances"]] == [f"{BCLD}/instances/i2"]


def test_validate_requires_permission(client):
    profile = post_profile(client)

    response = client.post(f"/profiles/{profile['uuid']}/validate")

    assert response.status_code == 403


# --- #339: can existing records move to the proposed version? ------------------

WORK = f"{BF}Work"
NOTE = Prop(f"{BF}note", repeatable=True)
DATE = Prop(f"{BF}date")
EXTENT = Prop(f"{BF}extent")
REMOVED = "property removed; its data would become unused RDF"


def values(**literals: str) -> dict:
    return {f"{BF}{name}": [{"@value": value}] for name, value in literals.items()}


def propose(client, profile: dict, data) -> dict:
    response = validate(client, profile, json={"data": json.dumps(data)})
    assert response.status_code == 200, response.text
    return response.json()


def put_profile(client, profile: dict, data) -> str:
    response = client.put(
        f"/profiles/{profile['uuid']}",
        headers=CATALOGER,
        json={"data": json.dumps(data)},
    )
    assert response.status_code == 200
    return response.json()["version_uri"]


def test_validate_data_that_is_not_a_template(client):
    profile = post_profile(client, json.dumps(template(WORK)))

    response = validate(client, profile, json={"data": json.dumps({"label": "x"})})

    assert response.status_code == 422
    assert "resource template" in response.json()["detail"]


def test_validate_reports_incompatible_instances(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    pinned = profile["version_uri"]
    dated = add_record(db_session, Work, "w1", pinned, values(date="1990"))
    add_record(db_session, Work, "w2", pinned, values(note="undated"))

    body = propose(client, profile, template(WORK, NOTE))

    assert body["requires_new_version"] is True
    assert body["incompatible_instances"] == [
        {
            "uri": dated,
            "version_uri": pinned,
            "problems": [
                {"subject": dated, "property": f"{BF}date", "reason": REMOVED}
            ],
        }
    ]
    assert {
        "kind": "property_removed",
        "property": f"{BF}date",
        "detail": "property removed",
        "breaking": True,
    } in body["changes"]


def test_validate_compares_each_record_with_its_own_version(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    v1 = profile["version_uri"]
    v2 = put_profile(client, profile, template(WORK, NOTE, DATE, EXTENT))
    # extent means nothing under v1, so dropping it can't break this one
    add_record(db_session, Work, "w1", v1, values(extent="1 v."))
    on_v2 = add_record(db_session, Work, "w2", v2, values(extent="1 v."))

    body = propose(client, profile, template(WORK, NOTE, DATE))

    assert [(i["uri"], i["version_uri"]) for i in body["incompatible_instances"]] == [
        (on_v2, v2)
    ]


def test_validate_breaking_change_no_record_uses(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    add_record(db_session, Work, "w1", profile["version_uri"], values(note="a"))

    body = propose(client, profile, template(WORK, NOTE))

    assert body["requires_new_version"] is False
    assert body["incompatible_instances"] == []
    assert any(c["breaking"] for c in body["changes"])


def test_validate_safe_change(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    add_record(db_session, Work, "w1", profile["version_uri"], values(date="1990"))

    body = propose(client, profile, template(WORK, DATE, NOTE, label="Renamed"))

    assert body["requires_new_version"] is False
    assert [c["kind"] for c in body["changes"]] == ["label_changed"]


def test_validate_skips_records_pinned_to_the_plain_profile_uri(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    add_record(db_session, Work, "w1", profile["uri"], values(date="1990"))

    body = propose(client, profile, template(WORK, NOTE))

    assert body["instance_count"] == 1
    assert body["requires_new_version"] is False


def test_validate_reads_ordered_values_as_stored(client, db_session):
    """Framing stores an ordered property as an @list; it must read back as one."""
    ordered = Prop(f"{BF}note", repeatable=True, ordered=True)
    profile = post_profile(client, json.dumps(template(WORK, ordered)))
    notes = {f"{BF}note": [{"@list": [{"@value": "a"}, {"@value": "b"}]}]}
    record = add_record(db_session, Work, "w1", profile["version_uri"], notes)

    body = propose(client, profile, template(WORK, Prop(f"{BF}note", ordered=True)))

    [instance] = body["incompatible_instances"]
    assert instance["uri"] == record
    assert [p["reason"] for p in instance["problems"]] == [
        "no longer repeatable, but it has more than one value"
    ]


TITLE = f"{BF}Title"
MAIN_TITLE = Prop(f"{BF}mainTitle")
SUBTITLE = Prop(f"{BF}subtitle")


def titled(title_ref: str):
    return template(WORK, Prop(f"{BF}title", "resource", nested=(title_ref,)))


def a_title(**literals: str) -> dict:
    return {f"{BF}title": [{"@type": [TITLE], **values(**literals)}]}


def test_validate_resolves_each_nested_version_once(client, db_session, monkeypatch):
    title = post_profile(client, json.dumps(template(TITLE, MAIN_TITLE, SUBTITLE)))
    title_v1 = title["version_uri"]
    title_v2 = put_profile(client, title, template(TITLE, MAIN_TITLE))
    work = post_profile(client, json.dumps(titled(title_v1)))
    for name in ("w1", "w2", "w3"):
        add_record(
            db_session,
            Work,
            name,
            work["version_uri"],
            a_title(mainTitle="Main", subtitle="Sub"),
        )
    calls = []

    def counting(db, uri):
        calls.append(uri)
        return resolve_version_uri(db, uri)

    monkeypatch.setattr(template_compat, "resolve_version_uri", counting)

    body = propose(client, work, titled(title_v2))

    assert len(body["incompatible_instances"]) == 3
    problem = body["incompatible_instances"][0]["problems"][0]
    assert (problem["property"], problem["reason"]) == (f"{BF}subtitle", REMOVED)
    assert sorted(calls) == sorted([work["version_uri"], title_v1, title_v2])


def test_validate_a_nested_profile_checks_no_records(client, db_session):
    """Records pinned to a parent move only when the parent is validated."""
    title = post_profile(client, json.dumps(template(TITLE, MAIN_TITLE, SUBTITLE)))
    work = post_profile(client, json.dumps(titled(title["version_uri"])))
    add_record(db_session, Work, "w1", work["version_uri"], a_title(subtitle="Sub"))

    body = propose(client, title, template(TITLE, MAIN_TITLE))

    assert body["unresolved_templates"] == []
    assert body["requires_new_version"] is False
    assert body["incompatible_instances"] == []
    assert [c["kind"] for c in body["changes"]] == ["property_removed"]


def test_validate_reports_templates_it_could_not_load(client, db_session):
    """A nested version that isn't stored is listed, and not assumed safe."""
    title = post_profile(client, json.dumps(template(TITLE, MAIN_TITLE, SUBTITLE)))
    work = post_profile(client, json.dumps(titled(title["version_uri"])))
    record = add_record(
        db_session, Work, "w1", work["version_uri"], a_title(mainTitle="Main")
    )
    missing = f"{title['uri']}/version/999999"

    body = propose(client, work, titled(missing))

    assert body["unresolved_templates"] == [missing]
    assert body["requires_new_version"] is True
    [instance] = body["incompatible_instances"]
    assert instance["uri"] == record
    assert [p["reason"] for p in instance["problems"]] == [
        f"could not load nested template {missing} to check it against"
    ]
    [bump] = [c for c in body["changes"] if c["kind"] == "nested_version_changed"]
    assert bump["breaking"] is True


def test_validate_a_stored_profile_that_cant_be_read(client):
    """Two ResourceTemplate nodes: listed as unresolved, not a 500."""
    profile = post_profile(client, json.dumps(template(WORK, NOTE)))
    other = template(WORK, uri="https://example.com/templates/other")
    put_profile(client, profile, template(WORK, NOTE) + other)

    body = propose(client, profile, template(WORK, NOTE, DATE))

    assert body["changes"] == []
    assert profile["uri"] in body["unresolved_templates"]


def test_validate_skips_records_it_cant_read(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    pinned = profile["version_uri"]
    dated = add_record(db_session, Work, "w1", pinned, values(date="1990"))
    unreadable = add_record(db_session, Work, "w2", pinned, values(date="1990"))
    # A Core UPDATE, so the ORM's framing hook doesn't fix the data up.
    db_session.execute(
        update(ResourceBase)
        .where(ResourceBase.uri == unreadable)
        .values(data={"@context": 5, HAS_RESOURCE_TEMPLATE: [{"@id": pinned}]})
    )
    db_session.commit()
    missing_version = add_record(
        db_session, Work, "w3", f"{profile['uri']}/version/999999", values(date="x")
    )

    body = propose(client, profile, template(WORK, NOTE))

    assert [i["uri"] for i in body["incompatible_instances"]] == [dated]
    assert body["unchecked_instances"] == [unreadable, missing_version]
    assert f"{profile['uri']}/version/999999" in body["unresolved_templates"]


# --- one resource against the latest version (#340) ------------------------------


def check_resource(client, profile: dict, resource_uri: str, data=None):
    body: dict = {"resource_uri": resource_uri}
    if data is not None:
        body["data"] = json.dumps(data)
    return validate(client, profile, json=body)


def test_validate_resource_unknown(client):
    profile = post_profile(client, json.dumps(template(WORK, NOTE)))

    response = check_resource(client, profile, f"{BCLD}/works/nope")

    assert response.status_code == 404


def test_validate_resource_not_a_record(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE)))
    hub = add_record(db_session, Hub, "h1", profile["version_uri"])

    response = check_resource(client, profile, hub)

    assert response.status_code == 404


def test_validate_resource_pinned_to_plain_profile_uri(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE)))
    record = add_record(db_session, Work, "w1", profile["uri"])

    response = check_resource(client, profile, record)

    assert response.status_code == 422


def test_validate_resource_pinned_to_another_profile(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE)))
    other = post_profile(client, json.dumps(template(WORK, NOTE)))
    record = add_record(db_session, Work, "w1", other["version_uri"])

    response = check_resource(client, profile, record)

    assert response.status_code == 422


def test_validate_resource_on_latest(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    record = add_record(
        db_session, Work, "w1", profile["version_uri"], values(date="1990")
    )

    response = check_resource(client, profile, record)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_latest"] is True
    assert body["compatible"] is True
    assert body["requires_new_version"] is False
    assert body["unchecked_instances"] == []
    assert body["resource_version_uri"] == profile["version_uri"]
    assert body["current_version_uri"] == profile["version_uri"]
    assert body["changes"] == []


def test_validate_resource_after_safe_edit(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    v1 = profile["version_uri"]
    record = add_record(db_session, Work, "w1", v1, values(date="1990"))
    v2 = put_profile(client, profile, template(WORK, NOTE, DATE, label="Renamed"))

    body = check_resource(client, profile, record).json()

    assert body["is_latest"] is False
    assert body["compatible"] is True
    assert body["requires_new_version"] is False
    assert body["unchecked_instances"] == []
    assert body["resource_version_uri"] == v1
    assert body["current_version_uri"] == v2
    assert [c["kind"] for c in body["changes"]] == ["label_changed"]
    assert body["incompatible_instances"] == []


def test_validate_resource_after_breaking_edit(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    v1 = profile["version_uri"]
    record = add_record(db_session, Work, "w1", v1, values(date="1990"))
    put_profile(client, profile, template(WORK, NOTE))

    body = check_resource(client, profile, record).json()

    assert body["compatible"] is False
    assert body["requires_new_version"] is True
    assert body["incompatible_instances"] == [
        {
            "uri": record,
            "version_uri": v1,
            "problems": [
                {"subject": record, "property": f"{BF}date", "reason": REMOVED}
            ],
        }
    ]


def test_validate_resource_only_that_resource(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    v1 = profile["version_uri"]
    record = add_record(db_session, Work, "w1", v1, values(date="1990"))
    add_record(db_session, Work, "w2", v1, values(date="1991"))
    put_profile(client, profile, template(WORK, NOTE))

    body = check_resource(client, profile, record).json()

    assert [i["uri"] for i in body["incompatible_instances"]] == [record]


def test_validate_resource_with_data(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    record = add_record(
        db_session, Work, "w1", profile["version_uri"], values(date="1990")
    )

    body = check_resource(client, profile, record, template(WORK, NOTE)).json()

    assert body["is_latest"] is True
    assert body["compatible"] is False
    assert body["requires_new_version"] is True
    assert [c["kind"] for c in body["changes"]] == ["property_removed"]
    assert body["incompatible_instances"][0]["problems"] == [
        {"subject": record, "property": f"{BF}date", "reason": REMOVED}
    ]


def test_validate_resource_pinned_to_a_parent_that_nests_it(client, db_session):
    """Records name only their root template, so a parent's pin isn't this one's."""
    title = post_profile(client, json.dumps(template(WORK, NOTE)))
    parent = post_profile(client, nesting(title["version_uri"]))
    record = add_record(db_session, Work, "w1", parent["version_uri"])

    response = check_resource(client, title, record)

    assert response.status_code == 422


def test_validate_resource_it_cant_read(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    missing = f"{profile['uri']}/version/999999"
    record = add_record(db_session, Work, "w1", missing, values(date="1990"))

    response = check_resource(client, profile, record)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unchecked_instances"] == [record]
    assert body["compatible"] is None
    assert body["requires_new_version"] is False
    assert body["incompatible_instances"] == []


def test_validate_resource_never_writes(client, db_session):
    profile = post_profile(client, json.dumps(template(WORK, NOTE, DATE)))
    record = add_record(
        db_session, Work, "w1", profile["version_uri"], values(date="1990")
    )
    stored_record = db_session.query(Work).filter(Work.uri == record).one().data
    versions_before = db_session.query(Version).count()

    response = check_resource(client, profile, record, template(WORK, NOTE))

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(Version).count() == versions_before
    assert db_session.query(Work).filter(Work.uri == record).one().data == (
        stored_record
    )
    stored = client.get(f"/profiles/{profile['uuid']}").json()
    assert stored["data"] == profile["data"]


def test_validate_without_resource_has_no_resource_fields(client):
    profile = post_profile(client, json.dumps(template(WORK, NOTE)))

    body = propose(client, profile, template(WORK, NOTE, DATE))

    assert body["resource_version_uri"] is None
    assert body["is_latest"] is None
    assert body["compatible"] is None
