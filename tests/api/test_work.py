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

test_work_uuid = "370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
test_work_bluecore_uri = f"https://api.sinopia.io/resources/{test_work_uuid}"
with pathlib.Path("tests/blue-core-work.jsonld").open() as fo:
    jsonld_data = json.load(fo)
orig_graph = load_jsonld(jsonld_data)

expanded_work_uuid = "7b7ed475-9126-4368-925a-8b8c5520250e"
expanded_work_uri = rdflib.URIRef(f"https://bcld.info/works/{expanded_work_uuid}")
eng_uri = rdflib.URIRef("http://id.loc.gov/vocabulary/languages/eng")
expanded_work_graph = init_graph()
expanded_work_graph.add((expanded_work_uri, rdflib.RDF.type, BF.Work))
expanded_work_graph.add((expanded_work_uri, BF.language, eng_uri))
with pathlib.Path("tests/blue-core-other-resources.json").open() as fo:
    eng_data = json.load(fo)


def add_test_work(db_session):
    db_session.add(
        Work(
            id=1,
            uuid=test_work_uuid,
            uri=test_work_bluecore_uri,
            data=jsonld_data,
        ),
    )
    db_session.commit()


def add_test_expanded_work(db_session):
    work = Work(
        id=1,
        uuid=expanded_work_uuid,
        uri=str(expanded_work_uri),
        data=json.loads(expanded_work_graph.serialize(format="json-ld")),
    )
    db_session.add(work)

    other_resource = OtherResource(id=2, uri=str(eng_uri), data=eng_data)
    db_session.add(other_resource)
    bf_other_resource = BibframeOtherResources(
        id=1,
        other_resource=other_resource,
        bibframe_resource=work,
    )
    db_session.add(bf_other_resource)
    db_session.commit()


def test_get_work_vnd_sinopia_json(client, db_session):
    # Note: since we are setting the JSON-LD data directly here on the Work model the
    # URI needs to match whats in the JSON-LD file or else the JSON-LD
    # framing will result in an empty graph.
    add_test_work(db_session)

    response = client.get(
        f"/works/{test_work_uuid}", headers={"Accept": "application/vnd.sinopia+json"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT

    assert data["uri"].startswith(test_work_bluecore_uri)

    fetched_graph = load_jsonld(data["data"])
    assert len(fetched_graph) == len(orig_graph)


def test_get_work_json(client, db_session):
    # Note: since we are setting the JSON-LD data directly here on the Work model the
    # URI needs to match whats in the JSON-LD file or else the JSON-LD
    # framing will result in an empty graph.
    add_test_work(db_session)

    response = client.get(
        f"/works/{test_work_uuid}", headers={"Accept": "application/json"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["@context"] == CONTEXT_URL
    data["@context"] = CONTEXT

    fetched_graph = load_jsonld(data)
    assert len(fetched_graph) == len(orig_graph)


def test_get_expanded_work(client, db_session):
    add_test_expanded_work(db_session)

    # Test regular GET response without expand parameter
    regular_work_response = client.get(f"/works/{expanded_work_uuid}.vnd.sinopia.json")
    data = regular_work_response.json()["data"]
    data["@context"] = CONTEXT
    regular_work_graph = load_jsonld(data)

    assert len(regular_work_graph) == 2

    # Test GET with expand = True
    expanded_work_response = client.get(
        f"/works/{expanded_work_uuid}?expand=true",
        headers={"Accept": "application/vnd.sinopia+json"},
    )
    data = expanded_work_response.json()["data"]
    assert data["@context"] == CONTEXT_URL
    data["@context"] = CONTEXT
    expanded_work_graph = load_jsonld(data)

    assert len(expanded_work_graph) == 5


def test_get_work_jsonld(client, db_session):
    add_test_work(db_session)

    response = client.get(
        f"/works/{test_work_uuid}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    assert response.json()["@id"] == test_work_bluecore_uri

    response = client.get(f"/works/{test_work_uuid}.jsonld")
    assert response.status_code == 200
    assert response.json()["@id"] == test_work_bluecore_uri
    assert response.json()["@context"] == CONTEXT_URL


def test_get_work_rdf_xml(client, db_session):
    add_test_work(db_session)

    response = client.get(
        f"/works/{test_work_uuid}", headers={"Accept": "application/rdf+xml"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/rdf+xml")

    response = client.get(f"/works/{test_work_uuid}.rdf")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/rdf+xml")


def test_get_work_ntriples(client, db_session):
    add_test_work(db_session)

    response = client.get(
        f"/works/{test_work_uuid}", headers={"Accept": "application/n-triples"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/n-triples")

    response = client.get(f"/works/{test_work_uuid}.nt")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/n-triples")


def test_get_work_turtle(client, db_session):
    add_test_work(db_session)

    response = client.get(f"/works/{test_work_uuid}", headers={"Accept": "text/turtle"})
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/turtle")

    response = client.get(f"/works/{test_work_uuid}.ttl")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/turtle")


def test_get_work_html(client, db_session):
    add_test_work(db_session)

    # Only a browser (Accept: text/html) on the clean URL gets the HTML view.
    response = client.get(f"/works/{test_work_uuid}", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert "BIBFRAME Work" in response.text
    # The view links to the alternative RDF serializations.
    assert f"{test_work_bluecore_uri}.ttl" in response.text

    # An unrecognized format (e.g. `.html`, `.xml`) falls through to the default
    # serialization, which is the HTML view.
    response = client.get(f"/works/{test_work_uuid}.html")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")


def test_get_work_html_orders_variant_titles_under_the_title(client, db_session):
    """
    The title proper, then its variants directly beneath it, then Type -- the way
    LC's own views read. Type used to be inserted at a fixed position and landed
    between the two title headings.
    """
    work_uuid = "7f6c1711-663b-4a7d-a196-21c5a953413c"
    db_session.add(
        Work(
            id=97,
            uuid=work_uuid,
            uri=f"https://bluecore.info/works/{work_uuid}",
            data={
                "@id": f"https://bluecore.info/works/{work_uuid}",
                "@type": ["Work", "Monograph"],
                "title": [
                    {
                        "@type": [
                            "VariantTitle",
                            "http://id.loc.gov/vocabulary/vartitletype/por",
                        ],
                        "mainTitle": "One thousand best movies on DVD",
                    },
                    {"@type": "Title", "mainTitle": "1,000 best movies on DVD"},
                ],
            },
        )
    )
    db_session.commit()

    response = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"})
    assert response.status_code == 200
    page = response.text

    # each title sits under its own heading
    assert "Other Titles (e.g. Variant)" in page
    title_at = page.index("1,000 best movies on DVD")
    variant_heading_at = page.index("Other Titles (e.g. Variant)")
    variant_at = page.index("One thousand best movies on DVD")
    type_at = page.index("Monograph")

    assert title_at < variant_heading_at < variant_at, "variants follow the title"
    assert variant_at < type_at, "Type comes after the titles, not between them"


def test_get_work_html_links_derived_from_to_the_source_record(client, db_session):
    """
    Derived from used to show a bare record number. It links to LC's readable
    page for that record, in a new tab since it leaves Blue Core.
    """
    work_uuid = "cd786d58-7adf-4f4e-aa40-3e0560330943"
    db_session.add(
        Work(
            id=96,
            uuid=work_uuid,
            uri=f"https://bluecore.info/works/{work_uuid}",
            data={
                "@id": f"https://bluecore.info/works/{work_uuid}",
                "@type": "Work",
                "title": {"@type": "Title", "mainTitle": "Derived Work"},
                "adminMetadata": {
                    "@type": "AdminMetadata",
                    "derivedFrom": {
                        "@id": "http://id.loc.gov/resources/works/23960506"
                    },
                },
            },
        )
    )
    db_session.commit()

    response = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"})
    assert response.status_code == 200
    page = response.text

    assert "Derived from:" in page
    assert (
        '<a href="https://id.loc.gov/resources/works/23960506.html"'
        ' target="_blank" rel="noopener noreferrer">23960506</a>'
    ) in page


# cbd requires work & instance and will be tested in test_cbd.py


def test_create_work(client, mocker, derived_from_sparql):
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-work.jsonld").read_text(), format="json-ld"
    )

    payload = {
        "data": original_graph.serialize(format="json-ld"),
    }
    create_response = client.post(
        "/works/", headers={"X-User": "cataloger"}, json=payload
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
        "https://api.sinopia.io/resources/370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
    )

    # Assert timestamps exist and are identical
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] == data["updated_at"], (
        "created_at and updated_at should match on creation"
    )


def test_update_work(client, db_session):
    payload = {
        "data": pathlib.Path("tests/blue-core-work.jsonld").read_text(),
    }
    create_response = client.post(
        "/works/", headers={"X-User": "cataloger"}, json=payload
    )

    assert create_response.status_code == 201

    data = create_response.json()
    data["data"]["@context"] = CONTEXT
    work_uri = rdflib.URIRef(data["uri"])
    work_graph = init_graph()
    data_str = json.dumps(data["data"])
    work_graph.parse(data=data_str, format="json-ld")

    work_graph.add(
        (
            work_uri,
            rdflib.URIRef("https://schema.org/name"),
            rdflib.Literal("A New Work Name"),
        )
    )
    work_uuid = create_response.json()["uri"].split("/")[-1]
    update_response = client.put(
        f"/works/{work_uuid}",
        headers={"X-User": "cataloger"},
        json={"data": work_graph.serialize(format="json-ld")},
    )

    assert update_response.status_code == 200
    assert update_response.json()["data"]["@context"] == CONTEXT_URL

    get_response = client.get(f"/works/{work_uuid}.vnd.sinopia.json")
    assert get_response.status_code == 200
    data = get_response.json()
    data["data"]["@context"] = CONTEXT

    updated_work_graph = init_graph()
    updated_work_graph.parse(data=data["data"], format="json-ld")

    name = updated_work_graph.value(
        subject=work_uri,
        predicate=rdflib.URIRef("https://schema.org/name"),
    )

    assert str(name) == "A New Work Name"

    # Assert timestamps exist and are now different
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] != data["updated_at"], (
        "created_at and updated_at should not match on update"
    )


def test_get_work_embedding_returns_501(client):
    response = client.get("/works/some-uuid/embeddings")
    assert response.status_code == 501


def test_create_work_embedding_returns_501(client):
    response = client.post(
        "/works/some-uuid/embeddings", headers={"X-User": "cataloger"}
    )
    assert response.status_code == 501


def test_delete_work(client, db_session):
    add_test_work(db_session)

    response = client.delete(
        f"/works/{test_work_uuid}", headers={"X-User": "cataloger"}
    )
    assert response.status_code == 204

    get_response = client.get(f"/works/{test_work_uuid}.vnd.sinopia.json")
    assert get_response.status_code == 404


def test_delete_work_not_found(client, db_session):
    response = client.delete(
        "/works/00000000-0000-0000-0000-000000000000",
        headers={"X-User": "cataloger"},
    )
    assert response.status_code == 404


def test_delete_work_cascades_to_instances(client, db_session):
    add_test_work(db_session)
    instance_uuid = "aaaaaaaa-0000-0000-0000-000000000001"
    instance_uri = f"https://bcld.info/instances/{instance_uuid}"
    instance = Instance(
        id=2,
        uuid=instance_uuid,
        uri=instance_uri,
        work_id=1,
        data=jsonld_data,
    )
    db_session.add(instance)
    db_session.commit()

    response = client.delete(
        f"/works/{test_work_uuid}", headers={"X-User": "cataloger"}
    )
    assert response.status_code == 204

    assert (
        db_session.query(Instance).filter(Instance.uuid == instance_uuid).first()
        is None
    )


def test_delete_work_with_other_resources(client, db_session):
    add_test_expanded_work(db_session)

    response = client.delete(
        f"/works/{expanded_work_uuid}", headers={"X-User": "cataloger"}
    )
    assert response.status_code == 204

    remaining = (
        db_session.query(BibframeOtherResources)
        .filter(BibframeOtherResources.id == 1)
        .first()
    )
    assert remaining is None


def test_delete_work_forbidden(client, db_session):
    add_test_work(db_session)

    response = client.delete(f"/works/{test_work_uuid}")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# bf:relation on the Work view: LC groups these under the relationship term,
# e.g. one "Series" heading holding the transcribed statement as plain text and
# the Hub that controls it as a link.
# ---------------------------------------------------------------------------
SERIES_RELATIONSHIP = "http://id.loc.gov/vocabulary/relationship/series"
HUB_LABEL = "Colección libro blanco de la ciudadanía"


def add_work_with_hub_relation(db_session, hub_uri, label=HUB_LABEL):
    """A Work naming its Hub the way the data actually carries it.

    works.hub_id stays null; the link is a bf:relation whose associatedResource
    is typed bf:Hub.
    """
    work_uuid = "b3f0c0de-0000-4000-8000-00000000f00d"
    uri = f"https://bcld.info/works/{work_uuid}"
    db_session.add(
        Work(
            id=41,
            uuid=work_uuid,
            uri=uri,
            data={
                "@id": uri,
                "@type": "Work",
                "title": {"@type": "Title", "mainTitle": "A work in a series"},
                "relation": {
                    "@type": "Relation",
                    "relationship": {"@id": SERIES_RELATIONSHIP},
                    "associatedResource": {
                        "@id": hub_uri,
                        "@type": ["Hub", "Series"],
                        "title": {"@type": "Title", "mainTitle": label},
                    },
                },
            },
        )
    )
    db_session.commit()
    return work_uuid


def test_get_work_html_names_a_hub_by_its_access_point(client, db_session):
    """
    LC writes the Hub as its name/title heading, not its plain title, so the
    Series line reads "King, Stephen, 1947-. Dark tower" rather than "Dark
    tower". Ours does the same, out of the Hub's own record.
    """
    hub_uuid = "052a7e69-8d84-6c2e-5015-76ac471f76ca"
    hub_uri = f"https://bcld.info/hubs/{hub_uuid}"
    access_point = "King, Stephen, 1947-. Dark tower"
    db_session.add(
        Hub(
            id=40,
            uuid=hub_uuid,
            uri=hub_uri,
            data={
                "@id": hub_uri,
                "@type": ["Hub", "Series"],
                "title": {"@type": "Title", "mainTitle": "Dark tower"},
                "rdfs:label": access_point,
            },
        )
    )
    # the Work's own copy of the label differs, to show which one is used
    work_uuid = add_work_with_hub_relation(db_session, hub_uri, label="A stale label")

    response = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    page = response.text
    # headed by the relationship term, the way LC heads it
    assert "<h2>Series</h2>" in page
    assert f'<a href="{hub_uri}">{access_point}</a>' in page
    assert "A stale label" not in page
    # the access point wins over the Hub's plain title
    assert ">Dark tower<" not in page


def test_get_work_html_links_a_hub_we_do_not_hold_at_its_source(client, db_session):
    """
    A Hub never ingested still gets a link -- to the source record's readable
    page, in a new tab, since following it leaves Blue Core.
    """
    hub_uri = "http://id.loc.gov/resources/hubs/052a7e69-8d84-6c2e-5015-76ac471f76ca"
    work_uuid = add_work_with_hub_relation(db_session, hub_uri)

    response = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    page = response.text
    assert "<h2>Series</h2>" in page
    # the label the Work carries, linked at LC's HTML view of that record
    lc_page = hub_uri.replace("http://", "https://") + ".html"
    assert f'href="{lc_page}"' in page
    assert HUB_LABEL in page
    assert 'target="_blank"' in page


def test_get_work_html_without_relations_has_no_relation_heading(client, db_session):
    work_uuid = "b3f0c0de-0000-4000-8000-0000000000aa"
    uri = f"https://bcld.info/works/{work_uuid}"
    db_session.add(
        Work(
            id=45,
            uuid=work_uuid,
            uri=uri,
            data={
                "@id": uri,
                "@type": "Work",
                "title": {"@type": "Title", "mainTitle": "A work with no relations"},
            },
        )
    )
    db_session.commit()

    response = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "<h2>Series</h2>" not in response.text


def add_dark_tower(db_session):
    """The exact shape ingestion produces, from the dev stack's Dark Tower record.

    Framing moves the Hub's description into the Hub record, so the Work is left
    holding a bare {"@id": ...} -- no @type, no title -- with the transcribed,
    uncontrolled series relation sitting right beside it under the same
    relationship. LC renders the pair as:

        Series
        The dark tower 4
        King, Stephen, 1947-. Dark tower 4.
    """
    hub_uuid = "85fed6fc-5367-45a4-affa-aa8e75ff0e30"
    hub_uri = f"http://localhost/hubs/{hub_uuid}"
    db_session.add(
        Hub(
            id=43,
            uuid=hub_uuid,
            uri=hub_uri,
            data={
                "@id": hub_uri,
                "@type": ["Hub", "Series"],
                "title": {"@type": "Title", "mainTitle": "Dark tower"},
                "rdfs:label": "King, Stephen, 1947-. Dark tower",
            },
        )
    )
    work_uuid = "b3f0c0de-0000-4000-8000-00000000cafe"
    uri = f"http://localhost/works/{work_uuid}"
    db_session.add(
        Work(
            id=44,
            uuid=work_uuid,
            uri=uri,
            data={
                "@id": uri,
                "@type": "Work",
                "title": {"@type": "Title", "mainTitle": "Wizard and glass"},
                "relation": [
                    {
                        "@type": "Relation",
                        "relationship": {"@id": SERIES_RELATIONSHIP},
                        "seriesEnumeration": "4",
                        "associatedResource": {
                            "@type": ["Series", "bflc:Uncontrolled"],
                            "title": {"@type": "Title", "mainTitle": "The dark tower"},
                            "status": [{"@id": TRANSCRIBED_STATUS}],
                        },
                    },
                    {
                        "@type": "Relation",
                        "relationship": {"@id": SERIES_RELATIONSHIP},
                        "seriesEnumeration": "4.",
                        "associatedResource": {"@id": hub_uri},
                    },
                ],
            },
        )
    )
    db_session.commit()
    return work_uuid, hub_uri


TRANSCRIBED_STATUS = "http://id.loc.gov/vocabulary/mstatus/t"


def test_get_work_html_reads_like_lcs_series_section(client, db_session):
    work_uuid, hub_uri = add_dark_tower(db_session)

    response = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    page = response.text
    # one heading for both relations, since they share a relationship term
    assert page.count("<h2>Series</h2>") == 1
    # the transcribed statement, enumerated and unlinked
    assert "<li>The dark tower 4</li>" in page
    # the Hub that controls it, enumerated, named by its access point, linked
    assert f'<li><a href="{hub_uri}">King, Stephen, 1947-. Dark tower 4.</a></li>' in (
        page
    )


def test_get_work_html_leaves_a_transcribed_series_unlinked(client, db_session):
    """A transcribed series statement has no uri of its own, so it cannot be a
    link -- it is plain text, as it is on LC's page."""
    work_uuid = "b3f0c0de-0000-4000-8000-00000000beef"
    uri = f"https://bcld.info/works/{work_uuid}"
    db_session.add(
        Work(
            id=42,
            uuid=work_uuid,
            uri=uri,
            data={
                "@id": uri,
                "@type": "Work",
                "title": {"@type": "Title", "mainTitle": "A work in a series"},
                "relation": {
                    "@type": "Relation",
                    "relationship": {"@id": SERIES_RELATIONSHIP},
                    "associatedResource": {
                        "@type": ["Series", "bflc:Uncontrolled"],
                        "title": {"@type": "Title", "mainTitle": HUB_LABEL},
                    },
                },
            },
        )
    )
    db_session.commit()

    response = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    page = response.text
    assert "<h2>Series</h2>" in page
    assert f"<li>{HUB_LABEL}</li>" in page
    assert f'<a href="{HUB_LABEL}"' not in page


if __name__ == "__main__":
    pytest.main()


def test_get_work_html_dashes_every_multi_valued_field(client, db_session):
    """Dashing is not a Hub-only treatment and not tied to particular fields:
    any field holding more than one value gets it, and single-valued ones do
    not. Admin Metadata is the exception -- see the test below."""
    add_test_work(db_session)

    page = client.get(f"/works/{test_work_uuid}", headers={"Accept": "text/html"}).text
    fields = dict(re.findall(r"<h2>([^<]+)</h2>(.*?)</div>", page, re.DOTALL))

    for label, block in fields.items():
        if label in ("Admin Metadata", "Alternative Formats", "Blue Core Editors"):
            continue
        values = block.count("<li")
        dashed = 'class="bc-bulleted"' in block
        assert dashed == (values > 1), f"{label}: {values} value(s), dashed={dashed}"

    # the fixture covers both sides of that rule
    assert 'class="bc-bulleted"' in fields["Type"]  # Text, Monograph
    assert 'class="bc-bulleted"' in fields["Subject"]
    assert 'class="bc-bulleted"' not in fields["Title"]


def test_get_work_html_leaves_admin_metadata_undashed(client, db_session):
    """Provenance is a set of statements about one event, not a list of
    alternatives, so it stays plain however many lines it runs to."""
    add_test_work(db_session)

    page = client.get(f"/works/{test_work_uuid}", headers={"Accept": "text/html"}).text
    blocks = [
        block
        for label, block in re.findall(r"<h2>([^<]+)</h2>(.*?)</div>", page, re.DOTALL)
        if label == "Admin Metadata"
    ]

    assert blocks, "fixture should carry admin metadata"
    for block in blocks:
        assert 'class="bc-bulleted"' not in block
    assert any(block.count("<li") > 1 for block in blocks), "and more than one line"


# ---------------------------------------------------------------------------
# Sidebar naming and multi-term relationships, checked against LC's page for
# work 23867197.
# ---------------------------------------------------------------------------
ONLINE_VERSION = "http://id.loc.gov/entities/relationships/onlineversion"
OTHER_PHYSICAL = "http://id.loc.gov/vocabulary/relationship/otherphysicalformat"


def test_get_work_html_names_an_instance_by_its_imprint(client, db_session):
    """
    LC's "Has Instance" reads "Hershey, PA: IGI Global, [2025]", not the title:
    every Instance of a Work carries the Work's title, so only the imprint tells
    two of them apart.
    """
    work_uuid = "8748735d-c211-4100-9048-168d04f9cfba"
    work_uri = f"http://localhost/works/{work_uuid}"
    work = Work(
        id=51,
        uuid=work_uuid,
        uri=work_uri,
        data={
            "@id": work_uri,
            "@type": "Work",
            "title": {
                "@type": "Title",
                "mainTitle": "Minority voices from the academic superstructure",
            },
        },
    )
    db_session.add(work)
    instance_uri = "http://localhost/instances/f669f974-4636-48e6-923a-d2ebe594d6c9"
    db_session.add(
        Instance(
            id=52,
            uuid="f669f974-4636-48e6-923a-d2ebe594d6c9",
            uri=instance_uri,
            work=work,
            data={
                "@id": instance_uri,
                "@type": "Instance",
                # the same title as its Work, which is exactly why it cannot be used
                "title": {
                    "@type": "Title",
                    "mainTitle": "Minority voices from the academic superstructure",
                },
                "publicationStatement": "Hershey, PA: IGI Global, [2025]",
            },
        )
    )
    db_session.commit()

    page = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"}).text

    assert f'<a href="{instance_uri}">Hershey, PA: IGI Global, [2025]</a>' in page


def test_get_work_html_assembles_an_imprint_without_a_statement(client, db_session):
    """No bf:publicationStatement, so the provision activity's simple parts are
    assembled into the same shape LC prints."""
    work_uuid = "8748735d-0000-4000-8000-000000000051"
    work_uri = f"http://localhost/works/{work_uuid}"
    work = Work(
        id=53,
        uuid=work_uuid,
        uri=work_uri,
        data={"@id": work_uri, "@type": "Work", "title": {"mainTitle": "A work"}},
    )
    db_session.add(work)
    instance_uri = "http://localhost/instances/f669f974-0000-4000-8000-000000000052"
    db_session.add(
        Instance(
            id=54,
            uuid="f669f974-0000-4000-8000-000000000052",
            uri=instance_uri,
            work=work,
            data={
                "@id": instance_uri,
                "@type": "Instance",
                "title": {"mainTitle": "A work"},
                "provisionActivity": {
                    "@type": ["ProvisionActivity", "Publication"],
                    "bflc:simplePlace": "Hershey, PA",
                    "bflc:simpleAgent": "IGI Global",
                    "bflc:simpleDate": "[2025]",
                },
            },
        )
    )
    db_session.commit()

    page = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"}).text

    assert "Hershey, PA: IGI Global, [2025]" in page


def test_get_work_html_heads_a_multi_term_relation_with_one_label(client, db_session):
    """
    One relation, two relationship terms. LC shows a single heading and takes the
    specific designator: "Online version", not "Other physical format" and not
    the two mashed together.
    """
    target_uri = "http://localhost/works/491eb535-0ee1-43ae-957f-b03184faaa5b"
    access_point = "Bailey, Erold K., 1965-. Minority voices"
    db_session.add(
        Work(
            id=55,
            uuid="491eb535-0ee1-43ae-957f-b03184faaa5b",
            uri=target_uri,
            data={"@id": target_uri, "@type": "Work", "bflc:aap": access_point},
        )
    )
    work_uuid = "8748735d-0000-4000-8000-000000000055"
    uri = f"http://localhost/works/{work_uuid}"
    db_session.add(
        Work(
            id=56,
            uuid=work_uuid,
            uri=uri,
            data={
                "@id": uri,
                "@type": "Work",
                "title": {"mainTitle": "Minority voices"},
                "relation": {
                    "@type": "Relation",
                    "relationship": [{"@id": OTHER_PHYSICAL}, {"@id": ONLINE_VERSION}],
                    "associatedResource": {"@id": target_uri},
                },
            },
        )
    )
    db_session.commit()

    page = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"}).text

    assert "<h2>Online version</h2>" in page
    assert "Otherphysicalformat" not in page
    assert "onlineversion" not in page
    assert "<h2>Other physical format</h2>" not in page
    assert f'<a href="{target_uri}">{access_point}</a>' in page
