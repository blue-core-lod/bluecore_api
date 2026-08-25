import json
import pathlib
import re

import pytest
import rdflib
from bluecore_models.models import (
    BibframeOtherResources,
    Hub,
    Instance,
    OtherResource,
    Work,
)
from bluecore_models.utils.graph import BF, CONTEXT, init_graph, load_jsonld

from bluecore_api.constants import CONTEXT_URL


def test_get_hub(client, db_session):
    test_hub_uuid = "62a26d82-4e65-c696-afed-b12d215a35b1"
    test_hub_uri = f"http://id.loc.gov/resources/hubs/{test_hub_uuid}"
    jsonld_data = json.loads(pathlib.Path("tests/blue-core-hub.jsonld").read_text())
    orig_graph = load_jsonld(jsonld_data)

    db_session.add(
        Hub(
            id=1,
            uuid=test_hub_uuid,
            uri=test_hub_uri,
            data=jsonld_data,
        )
    )

    response = client.get(
        f"/hubs/{test_hub_uuid}", headers={"Accept": "application/vnd.sinopia+json"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["uri"].startswith(test_hub_uri)
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT

    fetched_graph = load_jsonld(data["data"])
    assert len(fetched_graph) == len(orig_graph)


def test_get_expanded_hub(client, db_session):
    hub_uuid = "a1b2c3d4-0000-0000-0000-000000000001"
    hub_uri = rdflib.URIRef(f"https://bcld.info/hubs/{hub_uuid}")
    eng_uri = rdflib.URIRef("http://id.loc.gov/vocabulary/languages/eng")
    hub_graph = init_graph()
    hub_graph.add((hub_uri, rdflib.RDF.type, BF.Hub))
    hub_graph.add((hub_uri, BF.language, eng_uri))

    with pathlib.Path("tests/blue-core-other-resources.json").open() as fo:
        eng_data = json.load(fo)

    hub = Hub(
        id=1,
        uuid=hub_uuid,
        uri=str(hub_uri),
        data=json.loads(hub_graph.serialize(format="json-ld")),
    )
    db_session.add(hub)

    other_resource = OtherResource(id=2, uri=str(eng_uri), data=eng_data)
    db_session.add(other_resource)
    bf_other_resource = BibframeOtherResources(
        id=1,
        other_resource=other_resource,
        bibframe_resource=hub,
    )
    db_session.add(bf_other_resource)
    db_session.commit()

    regular_response = client.get(f"/hubs/{hub_uuid}.vnd.sinopia.json")
    data = regular_response.json()["data"]
    assert data["@context"] == CONTEXT_URL
    data["@context"] = CONTEXT

    regular_graph = load_jsonld(data)

    assert len(regular_graph) == 2

    expanded_response = client.get(f"/hubs/{hub_uuid}?expand=true")
    data = expanded_response.json()
    assert data["@context"] == CONTEXT_URL
    data["@context"] = CONTEXT
    expanded_graph = load_jsonld(data)

    assert len(expanded_graph) == 5


def test_create_hub(client, mocker, derived_from_sparql):
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-hub.jsonld").read_text(), format="json-ld"
    )

    payload = {
        "data": original_graph.serialize(format="json-ld"),
    }
    create_response = client.post(
        "/hubs/", headers={"X-User": "cataloger"}, json=payload
    )

    assert create_response.status_code == 201
    data = create_response.json()
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT
    new_graph = init_graph()
    new_graph.parse(data=data["data"], format="json-ld")

    assert len(original_graph) != len(new_graph)

    results = new_graph.query(derived_from_sparql)
    derived_from = results.bindings[0]["derived_from"]

    assert str(derived_from).startswith(
        "http://id.loc.gov/resources/hubs/62a26d82-4e65-c696-afed-b12d215a35b1"
    )

    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] == data["updated_at"], (
        "created_at and updated_at should match on creation"
    )


def test_update_hub(client, db_session):
    payload = {
        "data": pathlib.Path("tests/blue-core-hub.jsonld").read_text(),
    }
    create_response = client.post(
        "/hubs/", headers={"X-User": "cataloger"}, json=payload
    )

    assert create_response.status_code == 201

    data = create_response.json()
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT
    hub_uri = rdflib.URIRef(data["uri"])
    hub_graph = init_graph()
    data_str = json.dumps(data["data"])
    hub_graph.parse(data=data_str, format="json-ld")

    hub_graph.add(
        (
            hub_uri,
            rdflib.URIRef("https://schema.org/name"),
            rdflib.Literal("An Updated Hub Name"),
        )
    )
    hub_uuid = create_response.json()["uri"].split("/")[-1]
    update_response = client.put(
        f"/hubs/{hub_uuid}",
        headers={"X-User": "cataloger"},
        json={"data": hub_graph.serialize(format="json-ld")},
    )

    assert update_response.status_code == 200

    get_response = client.get(f"/hubs/{hub_uuid}.vnd.sinopia.json")
    assert get_response.status_code == 200
    data = get_response.json()
    data["data"]["@context"] = CONTEXT

    updated_hub_graph = init_graph()
    updated_hub_graph.parse(data=data["data"], format="json-ld")

    name = updated_hub_graph.value(
        subject=hub_uri,
        predicate=rdflib.URIRef("https://schema.org/name"),
    )

    assert str(name) == "An Updated Hub Name"

    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] != data["updated_at"], (
        "created_at and updated_at should not match on update"
    )


def test_get_hub_embedding_returns_501(client):
    response = client.get("/hubs/some-uuid/embeddings")
    assert response.status_code == 501


def test_create_hub_embedding_returns_501(client):
    response = client.post(
        "/hubs/some-uuid/embeddings", headers={"X-User": "cataloger"}
    )
    assert response.status_code == 501


def test_delete_hub(client, db_session):
    test_hub_uuid = "62a26d82-4e65-c696-afed-b12d215a35b1"
    test_hub_uri = f"http://id.loc.gov/resources/hubs/{test_hub_uuid}"
    with pathlib.Path("tests/blue-core-hub.jsonld").open() as f:
        jsonld_data = json.load(f)
    db_session.add(Hub(id=1, uuid=test_hub_uuid, uri=test_hub_uri, data=jsonld_data))
    db_session.commit()

    response = client.delete(f"/hubs/{test_hub_uuid}", headers={"X-User": "cataloger"})
    assert response.status_code == 204

    get_response = client.get(f"/hubs/{test_hub_uuid}.vnd.sinopia.json")
    assert get_response.status_code == 404


def test_delete_hub_not_found(client, db_session):
    response = client.delete(
        "/hubs/00000000-0000-0000-0000-000000000000",
        headers={"X-User": "cataloger"},
    )
    assert response.status_code == 404


def test_delete_hub_cascades_to_works_and_instances(client, db_session):
    hub_uuid = "aaaaaaaa-1111-0000-0000-000000000001"
    hub_uri = f"https://bcld.info/hubs/{hub_uuid}"
    hub_graph = init_graph()
    hub_graph.add((rdflib.URIRef(hub_uri), rdflib.RDF.type, BF.Hub))
    hub = Hub(
        id=1,
        uuid=hub_uuid,
        uri=hub_uri,
        data=json.loads(hub_graph.serialize(format="json-ld")),
    )
    db_session.add(hub)
    db_session.flush()

    work_uuid = "bbbbbbbb-2222-0000-0000-000000000002"
    work_uri = f"https://bcld.info/works/{work_uuid}"
    work_graph = init_graph()
    work_graph.add((rdflib.URIRef(work_uri), rdflib.RDF.type, BF.Work))
    work = Work(
        id=2,
        uuid=work_uuid,
        uri=work_uri,
        hub_id=1,
        data=json.loads(work_graph.serialize(format="json-ld")),
    )
    db_session.add(work)
    db_session.flush()

    instance_uuid = "cccccccc-3333-0000-0000-000000000003"
    instance_uri = f"https://bcld.info/instances/{instance_uuid}"
    instance_graph = init_graph()
    instance_graph.add((rdflib.URIRef(instance_uri), rdflib.RDF.type, BF.Instance))
    instance = Instance(
        id=3,
        uuid=instance_uuid,
        uri=instance_uri,
        work_id=2,
        data=json.loads(instance_graph.serialize(format="json-ld")),
    )
    db_session.add(instance)
    db_session.commit()

    response = client.delete(f"/hubs/{hub_uuid}", headers={"X-User": "cataloger"})
    assert response.status_code == 204

    assert db_session.query(Hub).filter(Hub.uuid == hub_uuid).first() is None
    assert db_session.query(Work).filter(Work.uuid == work_uuid).first() is None
    assert (
        db_session.query(Instance).filter(Instance.uuid == instance_uuid).first()
        is None
    )


def test_delete_hub_forbidden(client, db_session):
    test_hub_uuid = "62a26d82-4e65-c696-afed-b12d215a35b1"
    test_hub_uri = f"http://id.loc.gov/resources/hubs/{test_hub_uuid}"
    with pathlib.Path("tests/blue-core-hub.jsonld").open() as f:
        jsonld_data = json.load(f)
    db_session.add(Hub(id=1, uuid=test_hub_uuid, uri=test_hub_uri, data=jsonld_data))
    db_session.commit()

    response = client.delete(f"/hubs/{test_hub_uuid}")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# The Hub view: the human-facing page, and the Works it gathers
# ---------------------------------------------------------------------------
hub_view_uuid = "62a26d82-4e65-c696-afed-b12d215a35b1"
hub_view_uri = f"http://id.loc.gov/resources/hubs/{hub_view_uuid}"
# The fixture Hub's title, as the template escapes it (the apostrophe becomes an
# entity), so the assertions match what a reader actually receives.
HUB_TITLE = "Chŏngch&#39;aek yŏn&#39;gu sirijŭ"


def add_view_hub(db_session):
    jsonld_data = json.loads(pathlib.Path("tests/blue-core-hub.jsonld").read_text())
    hub = Hub(id=1, uuid=hub_view_uuid, uri=hub_view_uri, data=jsonld_data)
    db_session.add(hub)
    db_session.commit()
    return hub


def add_work_in_hub(db_session, id_, uuid_, title, hub_uri=hub_view_uri):
    """A Work linked to its Hub by works.hub_id -- how the link is actually stored.

    Ingest sets the foreign key from bf:expressionOf, so the Work keeps that
    predicate in its own data too. A hub_uri we hold no record for leaves the
    key null, which is what an unresolvable reference looks like.
    """
    uri = f"https://bcld.info/works/{uuid_}"
    hub = db_session.query(Hub).filter(Hub.uri == hub_uri).one_or_none()
    work = Work(
        id=id_,
        uuid=uuid_,
        uri=uri,
        hub_id=hub.id if hub is not None else None,
        data={
            "@id": uri,
            "@type": "Work",
            "title": {"@type": "Title", "mainTitle": title},
            "expressionOf": {"@id": hub_uri},
        },
    )
    db_session.add(work)
    db_session.commit()
    return work


def test_get_hub_html(client, db_session):
    """A browser asking for a Hub gets the view page, not the JSON-LD."""
    add_view_hub(db_session)

    response = client.get(f"/hubs/{hub_view_uuid}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    page = response.text
    assert "BIBFRAME Hub" in page
    # The Hub's own title and its variant, each under their own heading
    assert HUB_TITLE in page
    assert "Other Titles (e.g. Variant)" in page
    assert "정책 연구 시리즈" in page
    # LC lists "Hub" under Type; only bf:Work, which the fixture also carries, is
    # left out, since every Hub is one and the heading does not claim it.
    assert "<h2>Type</h2>" in page
    assert "Hub" in page
    assert ">Work<" not in page
    # and the alternative serializations are linked, as on the other views
    assert f"{hub_view_uri}.ttl" in page


def test_get_hub_still_defaults_to_jsonld(client, db_session):
    """API clients that ask for no format keep getting JSON-LD, as before."""
    add_view_hub(db_session)

    response = client.get(f"/hubs/{hub_view_uuid}")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/ld+json")


def test_get_hub_html_lists_associated_works(client, db_session):
    add_view_hub(db_session)
    work_uri = add_work_in_hub(
        db_session, 2, "8f1c4f8e-0000-4000-8000-000000000001", "Chaesaeng enŏji"
    ).uri

    response = client.get(f"/hubs/{hub_view_uuid}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    page = response.text
    assert "Associated Works" in page
    assert f'href="{work_uri}"' in page
    assert "Chaesaeng enŏji" in page


def test_get_hub_html_without_works_has_no_heading(client, db_session):
    """A Hub nothing points at yet renders, just without the sidebar section."""
    add_view_hub(db_session)

    response = client.get(f"/hubs/{hub_view_uuid}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "Associated Works" not in response.text


def test_get_hub_html_ignores_works_in_another_hub(client, db_session):
    """The lookup follows this Hub's foreign key, not merely any Work that has one."""
    add_view_hub(db_session)
    other_hub = _stub(
        db_session,
        4,
        "hub",
        "00000000-0000-0000-0000-000000000000",
        "Some other series",
    )
    other_uri = add_work_in_hub(
        db_session,
        3,
        "8f1c4f8e-0000-4000-8000-000000000002",
        "Some other series title",
        hub_uri=other_hub,
    ).uri

    response = client.get(f"/hubs/{hub_view_uuid}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert f'href="{other_uri}"' not in response.text


# ---------------------------------------------------------------------------
# A fully described Hub points back out at everything it gathers. LC's page
# heads each relationship separately and names every target by its access point.
# ---------------------------------------------------------------------------
RELATIONSHIP = "http://id.loc.gov/vocabulary/relationship/"
RELATED_TO = "http://id.loc.gov/ontologies/bibframe/relatedTo"

dark_tower_uuid = "85fed6fc-5367-45a4-affa-aa8e75ff0e30"
dark_tower_uri = f"http://localhost/hubs/{dark_tower_uuid}"


def _stub(db_session, id_, kind, uuid_, access_point):
    """A record ingestion minted for the other end of a relation: an access point
    and little else, which is all the linking Hub needs from it."""
    uri = f"http://localhost/{kind}s/{uuid_}"
    model = Hub if kind == "hub" else Work
    db_session.add(
        model(
            id=id_,
            uuid=uuid_,
            uri=uri,
            data={
                "@id": uri,
                "@type": ["Hub", "Series"] if kind == "hub" else "Work",
                "bflc:aap": access_point,
            },
        )
    )
    return uri


def add_described_dark_tower(db_session):
    """The Dark Tower Hub with its full description, as the dev stack holds it.

    Every associatedResource is a bare {"@id": ...} pointing at a record
    ingestion minted, so each line's text has to come from that record.
    """
    wizard = _stub(
        db_session,
        11,
        "work",
        "3450e5bf-0eb6-4b6e-891e-d5a1a229a017",
        "King, Stephen, 1947-. Wizard and glass",
    )
    waste_lands = _stub(
        db_session,
        12,
        "work",
        "68b1dc93-349c-498d-b1f4-98aadd8e7ac8",
        "King, Stephen, 1947-. The waste lands",
    )
    gunslinger = _stub(
        db_session,
        13,
        "work",
        "be803d8e-49aa-4013-a75b-540b9894b917",
        "David, Peter (Peter Allen). The gunslinger born",
    )
    way_station = _stub(
        db_session,
        14,
        "work",
        "0af5aa8b-202d-4291-b443-8efa464cb795",
        "David, Peter (Peter Allen). The way station",
    )
    korean = _stub(
        db_session,
        15,
        "hub",
        "00bdbc71-ef52-4483-afc9-9eb59b340846",
        "King, Stephen, 1947-. Dark tower. Korean",
    )
    eluria = _stub(
        db_session,
        16,
        "hub",
        "86e66da3-1f4e-4d0f-b7ce-54c52cce5c8b",
        "King, Stephen, 1947-. Little Sisters of Eluria",
    )

    def relation(term, target):
        return {
            "@type": "Relation",
            "relationship": {"@id": term},
            "associatedResource": {"@id": target},
        }

    db_session.add(
        Hub(
            id=10,
            uuid=dark_tower_uuid,
            uri=dark_tower_uri,
            data={
                "@id": dark_tower_uri,
                "@type": ["Hub", "Series"],
                "title": {"@type": "Title", "mainTitle": "Dark tower"},
                "rdfs:label": "King, Stephen, 1947-. Dark tower",
                # deliberately not in LC's display order, to show the ordering
                "relation": [
                    relation(RELATED_TO, eluria),
                    relation(f"{RELATIONSHIP}translatedas", korean),
                    relation(f"{RELATIONSHIP}relatedwork", gunslinger),
                    relation(f"{RELATIONSHIP}seriesof", wizard),
                    relation(f"{RELATIONSHIP}seriesof", waste_lands),
                    relation(f"{RELATIONSHIP}partof", way_station),
                ],
            },
        )
    )
    db_session.commit()
    return {"wizard": wizard, "waste_lands": waste_lands, "korean": korean}


def test_get_hub_html_lists_its_own_relations(client, db_session):
    uris = add_described_dark_tower(db_session)

    response = client.get(f"/hubs/{dark_tower_uuid}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    page = response.text
    # a heading per relationship, spelled the way LC spells it
    for heading in (
        "Series of",
        "Related work",
        "Part of",
        "Translated as",
        "Related To",
    ):
        assert f"<h2>{heading}</h2>" in page, heading
    # every target named by its access point and linked to its own record,
    # Works and other Hubs alike
    assert (
        f'<a href="{uris["wizard"]}">King, Stephen, 1947-. Wizard and glass</a>' in page
    )
    assert (
        f'<a href="{uris["korean"]}">King, Stephen, 1947-. Dark tower. Korean</a>'
        in page
    )


def test_get_hub_html_orders_sections_like_lc(client, db_session):
    """LC's order, not the order our stored bf:relation happens to be in."""
    add_described_dark_tower(db_session)

    response = client.get(f"/hubs/{dark_tower_uuid}", headers={"Accept": "text/html"})

    page = response.text
    headings = [
        page.index(f"<h2>{h}</h2>")
        for h in ("Series of", "Related work", "Part of", "Translated as", "Related To")
    ]
    assert headings == sorted(headings)


def test_get_hub_html_groups_repeated_relationships_under_one_heading(
    client, db_session
):
    uris = add_described_dark_tower(db_session)

    response = client.get(f"/hubs/{dark_tower_uuid}", headers={"Accept": "text/html"})

    page = response.text
    assert page.count("<h2>Series of</h2>") == 1
    series_of = page.index("<h2>Series of</h2>")
    next_heading = page.index("<h2>", series_of + 4)
    section = page[series_of:next_heading]
    assert uris["wizard"] in section
    assert uris["waste_lands"] in section


def test_get_hub_html_does_not_repeat_a_work_it_already_names(client, db_session):
    """
    The reverse lookup and the Hub's own seriesof relation both find Wizard and
    glass. It should be listed once, under the relationship the Hub asserts.
    """
    uris = add_described_dark_tower(db_session)
    # the foreign key points back at the Hub, which is what works_for_hub follows
    work = db_session.query(Work).filter(Work.uri == uris["wizard"]).one()
    work.hub_id = 10
    db_session.commit()

    response = client.get(f"/hubs/{dark_tower_uuid}", headers={"Accept": "text/html"})

    page = response.text
    assert page.count(f'href="{uris["wizard"]}"') == 1
    assert "Associated Works" not in page


def test_get_hub_html_still_lists_a_work_it_does_not_name(client, db_session):
    """A Work added since the Hub was described still shows up, under its own
    heading -- the Hub's data has no relation naming it."""
    add_described_dark_tower(db_session)
    newcomer = add_work_in_hub(
        db_session,
        20,
        "8f1c4f8e-0000-4000-8000-000000000099",
        "Song of Susannah",
        hub_uri=dark_tower_uri,
    ).uri

    response = client.get(f"/hubs/{dark_tower_uuid}", headers={"Accept": "text/html"})

    page = response.text
    assert "<h2>Associated Works</h2>" in page
    assert f'href="{newcomer}"' in page


def test_get_hub_html_cannot_load_to_marva(client, db_session):
    """Marva loads Instances; a Hub gets the same disabled link a Work does."""
    add_view_hub(db_session)

    response = client.get(f"/hubs/{hub_view_uuid}", headers={"Accept": "text/html"})

    page = response.text
    assert "Marva loads Instances, not Hubs." in page
    assert f"?resource={hub_view_uri}" not in page


if __name__ == "__main__":
    pytest.main()


# ---------------------------------------------------------------------------
# Vocabulary terms a record cites but has no attachment row for. The Dark Tower
# Hub has zero bibframe_other_resources rows, yet its agent, relator and status
# are all in the OtherResource table from other records' ingests.
# ---------------------------------------------------------------------------
AGENT = "http://id.loc.gov/rwo/agents/n79063767"
CTB = "http://id.loc.gov/vocabulary/relators/ctb"
CANCINV = "http://id.loc.gov/vocabulary/mstatus/cancinv"


def add_unattached_hub(db_session):
    """A Hub citing terms held as OtherResources but joined to nothing."""
    db_session.add(
        OtherResource(
            id=90,
            uri=AGENT,
            data={
                "@id": AGENT,
                "@type": ["Agent", "Person"],
                "rdfs:label": "King, Stephen, 1947-",
            },
        )
    )
    # a Role carries a code and no label at all, so nothing here can resolve it
    db_session.add(
        OtherResource(id=91, uri=CTB, data={"@id": CTB, "@type": "Role", "code": "ctb"})
    )
    db_session.add(
        OtherResource(
            id=92,
            uri=CANCINV,
            data={
                "@id": CANCINV,
                "@type": "Status",
                "code": "cancinv",
                "rdfs:label": "canceled or invalid",
            },
        )
    )
    uuid_ = "85fed6fc-0000-4000-8000-0000000000cc"
    uri = f"http://localhost/hubs/{uuid_}"
    db_session.add(
        Hub(
            id=93,
            uuid=uuid_,
            uri=uri,
            data={
                "@id": uri,
                "@type": ["Hub", "Series"],
                "title": {"@type": "Title", "mainTitle": "Dark tower"},
                "contribution": {
                    "@type": ["Contribution", "PrimaryContribution"],
                    "agent": {"@id": AGENT},
                    "role": {"@id": CTB},
                },
                "identifiedBy": {
                    "@type": "Lccn",
                    "status": {"@id": CANCINV},
                    "rdf:value": "n 2003044804",
                },
                "note": [
                    {
                        "@type": [
                            "Note",
                            "http://id.loc.gov/vocabulary/mnotetype/descsource",
                        ],
                        "rdfs:label": "Created from auth.",
                    },
                    {
                        "@type": [
                            "Note",
                            "http://id.loc.gov/vocabulary/mnotetype/datasource",
                        ],
                        "rdfs:label": "t.p. (A Dark tower novel)",
                    },
                ],
                "genreForm": {
                    "@type": "GenreForm",
                    "rdfs:label": "Series (Publications)",
                },
                "originPlace": {"@type": "Place", "rdfs:label": "West Knigston (R.I.)"},
            },
        )
    )
    db_session.commit()
    return uuid_


def test_get_hub_html_resolves_terms_it_is_not_joined_to(client, db_session):
    """The agent's name and the status label come from OtherResources this Hub
    has no attachment row for -- it cites them, which is enough."""
    uuid_ = add_unattached_hub(db_session)

    page = client.get(f"/hubs/{uuid_}", headers={"Accept": "text/html"}).text

    assert f'<a href="{AGENT}">King, Stephen, 1947-</a>' in page
    # the bare identifier was the link text before the term resolved
    assert ">n79063767<" not in page
    assert "Lccn: n 2003044804 (canceled or invalid)" in page
    assert "(cancinv)" not in page


def test_get_hub_html_spells_out_the_relator_code(client, db_session):
    """The stored Role has a code and no label, so the spelling comes from
    RELATOR_LABELS -- and the role links to its own vocabulary term, separately
    from the agent it describes."""
    uuid_ = add_unattached_hub(db_session)

    page = client.get(f"/hubs/{uuid_}", headers={"Accept": "text/html"}).text

    assert f'(<a href="{CTB}">contributor</a>)' in page
    assert "(ctb)" not in page


def test_get_hub_html_leads_notes_with_their_kind(client, db_session):
    uuid_ = add_unattached_hub(db_session)

    page = client.get(f"/hubs/{uuid_}", headers={"Accept": "text/html"}).text

    assert "description source: Created from auth." in page
    assert "data source: t.p. (A Dark tower novel)" in page


def _field_blocks(page: str) -> dict[str, str]:
    """The rendered markup of each field, keyed by its heading."""
    return dict(re.findall(r"<h2>([^<]+)</h2>(.*?)</div>", page, re.DOTALL))


def test_get_hub_html_dashes_only_where_there_is_a_list(client, db_session):
    """The count is the whole rule -- any field with more than one value is
    dashed. The fixture Hub has Type and Note with two values each, and
    Identified by, Place of Origin, Title, Contribution and Genre Form with one
    apiece."""
    uuid_ = add_unattached_hub(db_session)

    fields = _field_blocks(
        client.get(f"/hubs/{uuid_}", headers={"Accept": "text/html"}).text
    )

    for label in ("Type", "Note"):
        assert 'class="bc-bulleted"' in fields[label], label
        assert fields[label].count("<li") > 1, label
    # every single-valued field reads as a statement -- LC leaves these plain,
    # whatever the field is
    for label in (
        "Identified by",
        "Place of Origin",
        "Title",
        "Contribution",
        "Genre Form",
    ):
        assert 'class="bc-bulleted"' not in fields[label], label
        assert fields[label].count("<li") <= 1, label


def test_get_hub_html_dashes_a_field_only_once_it_holds_two_values(client, db_session):
    """The dash follows the count, not the label: the same field is plain on a
    Hub carrying one identifier and dashed on one carrying two."""
    one = {"@type": "Lccn", "rdf:value": "n 84743102"}
    two = {"@type": "Lccn", "rdf:value": "n 2003044804"}

    def add(id_, uuid_, identified_by):
        uri = f"http://localhost/hubs/{uuid_}"
        db_session.add(
            Hub(
                id=id_,
                uuid=uuid_,
                uri=uri,
                data={
                    "@id": uri,
                    "@type": ["Hub", "Series"],
                    "title": {"@type": "Title", "mainTitle": "Dark tower"},
                    "identifiedBy": identified_by,
                },
            )
        )
        return uuid_

    single = add(97, "85fed6fc-0000-4000-8000-0000000000ee", one)
    double = add(98, "85fed6fc-0000-4000-8000-0000000000ff", [one, two])
    db_session.commit()

    plain = _field_blocks(
        client.get(f"/hubs/{single}", headers={"Accept": "text/html"}).text
    )["Identified by"]
    assert 'class="bc-bulleted"' not in plain

    dashed = _field_blocks(
        client.get(f"/hubs/{double}", headers={"Accept": "text/html"}).text
    )["Identified by"]
    assert 'class="bc-bulleted"' in dashed
    assert dashed.count("<li") == 2


def test_get_hub_html_names_places_once_their_authorities_are_held(client, db_session):
    """
    Place of Origin renders bare identifiers only because the place authorities
    are absent: LC's source document gives n80126293 the label "New York
    (State)", but ingestion did not create an OtherResource for it. The view
    needs no change -- adding the record is enough.
    """
    ny_state = "http://id.loc.gov/rwo/agents/n80126293"
    uuid_ = "85fed6fc-0000-4000-8000-0000000000dd"
    uri = f"http://localhost/hubs/{uuid_}"
    db_session.add(
        Hub(
            id=95,
            uuid=uuid_,
            uri=uri,
            data={
                "@id": uri,
                "@type": ["Hub", "Series"],
                "title": {"@type": "Title", "mainTitle": "Dark tower"},
                "originPlace": [
                    {"@type": "Place", "rdfs:label": "West Knigston (R.I.)"},
                    {"@id": ny_state},
                ],
            },
        )
    )
    db_session.commit()

    # absent: the reference is all the page has to show
    page = client.get(f"/hubs/{uuid_}", headers={"Accept": "text/html"}).text
    assert "n80126293" in page
    assert "New York (State)" not in page

    db_session.add(
        OtherResource(
            id=96,
            uri=ny_state,
            data={
                "@id": ny_state,
                "@type": "mads:Geographic",
                "rdfs:label": "New York (State)",
            },
        )
    )
    db_session.commit()

    page = client.get(f"/hubs/{uuid_}", headers={"Accept": "text/html"}).text
    assert "New York (State)" in page
    assert ">n80126293<" not in page


def test_get_hub_html_shows_genre_form_and_place_of_origin(client, db_session):
    uuid_ = add_unattached_hub(db_session)

    page = client.get(f"/hubs/{uuid_}", headers={"Accept": "text/html"}).text

    assert "<h2>Genre Form</h2>" in page
    assert "Series (Publications)" in page
    assert "<h2>Place of Origin</h2>" in page
    assert "West Knigston (R.I.)" in page
