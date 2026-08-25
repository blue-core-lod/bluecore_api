import json
import pathlib
import re
from typing import Any

import pytest
import rdflib
from bluecore_models.models import (
    BibframeOtherResources,
    Instance,
    OtherResource,
    Work,
)
from bluecore_models.utils.graph import BF, CONTEXT, init_graph, load_jsonld

from bluecore_api.app.utils.serialize.response_generator import CONTEXT_URL

test_instance_uuid = "75d831b9-e0d6-40f0-abb3-e9130622eb8a"
test_instance_bluecore_uri = f"https://bluecore.info/instances/{test_instance_uuid}"
jsonld_data = json.loads(pathlib.Path("tests/blue-core-instance.jsonld").read_text())
orig_graph = load_jsonld(jsonld_data)

test_expanded_instance_uuid = "1e09c839-474d-4ab5-8b44-479e08927045"
test_expanded_instance_uri = rdflib.URIRef(
    f"https://bcld.info/instances/{test_instance_uuid}"
)
kor_uri = rdflib.URIRef("http://id.loc.gov/vocabulary/languages/kor")
test_expanded_instance_graph = init_graph()
test_expanded_instance_graph.add(
    (test_expanded_instance_uri, rdflib.RDF.type, BF.Instance)
)
test_expanded_instance_graph.add((test_expanded_instance_uri, BF.language, kor_uri))
with pathlib.Path("tests/blue-core-other-resources2.json").open() as fo:
    kor_data = json.load(fo)


def add_test_instance(db_session):
    db_session.add(
        Instance(
            id=1,
            uuid=test_instance_uuid,
            uri=str(test_instance_bluecore_uri),
            data=json.loads(orig_graph.serialize(format="json-ld")),
        )
    )
    db_session.commit()


def add_test_expanded_instance(db_session):
    instance = Instance(
        id=1,
        uuid=test_expanded_instance_uuid,
        uri=str(test_expanded_instance_uri),
        data=json.loads(test_expanded_instance_graph.serialize(format="json-ld")),
    )

    db_session.add(instance)
    other_resource = OtherResource(id=2, uri=str(kor_uri), data=kor_data)
    db_session.add(other_resource)
    bf_other_resource = BibframeOtherResources(
        id=1, other_resource=other_resource, bibframe_resource=instance
    )
    db_session.add(bf_other_resource)
    db_session.commit()


def test_get_instance_sinopia_json(client, db_session):
    add_test_instance(db_session)

    response = client.get(f"/instances/{test_instance_uuid}.vnd.sinopia.json")
    assert response.status_code == 200

    assert response.json()["uri"].startswith(test_instance_bluecore_uri)

    assert response.json()["data"]["@context"] == CONTEXT_URL
    data = response.json()["data"]
    data["@context"] = CONTEXT
    fetched_graph = load_jsonld(data)
    assert len(orig_graph) == len(fetched_graph), "graph lengths are the same"


def test_get_expanded_instance_sinopia_json(client, db_session):
    add_test_expanded_instance(db_session)

    # Regular Get Call for Instance and application/vnd.sinopia+json format
    regular_instance_result = client.get(
        f"/instances/{test_expanded_instance_uuid}",
        headers={"Accept": "application/vnd.sinopia+json"},
    )
    assert regular_instance_result.json()["data"]["@context"] == CONTEXT_URL
    data: dict[str, Any] = regular_instance_result.json()["data"]
    data["@context"] = CONTEXT
    regular_instance_graph = load_jsonld(data)

    assert len(regular_instance_graph) == 2

    # Test GET with expand = True
    expanded_instance_result = client.get(
        f"/instances/{test_expanded_instance_uuid}?expand=true",
        headers={"Accept": "application/vnd.sinopia+json"},
    )
    data = expanded_instance_result.json()["data"]
    data["@context"] = CONTEXT
    expanded_instance_graph = load_jsonld(data)

    assert len(expanded_instance_graph) == 5

    # Test GET with expand = False and .vnd.sinopia.json format
    expand_false_result = client.get(
        f"/instances/{test_expanded_instance_uuid}.vnd.sinopia.json?expand=false",
    )
    data = expand_false_result.json()["data"]
    data["@context"] = CONTEXT
    expand_false_graph = load_jsonld(data)

    assert len(expand_false_graph) == len(regular_instance_graph)


def test_get_instance_jsonld(client, db_session):
    add_test_instance(db_session)

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    assert response.json()["@id"] == test_instance_bluecore_uri

    response = client.get(f"/instances/{test_instance_uuid}.jsonld")
    assert response.status_code == 200
    assert response.json()["@id"] == test_instance_bluecore_uri
    assert response.json()["@context"] == CONTEXT_URL


def test_get_instance_json(client, db_session):
    add_test_instance(db_session)

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "application/json"}
    )
    assert response.status_code == 200
    assert response.json()["@id"] == test_instance_bluecore_uri

    response = client.get(f"/instances/{test_instance_uuid}.json")
    assert response.status_code == 200
    assert response.json()["@id"] == test_instance_bluecore_uri
    assert response.json()["@context"] == CONTEXT_URL


def test_get_instance_rdf_xml(client, db_session):
    add_test_instance(db_session)

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "application/rdf+xml"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/rdf+xml")

    response = client.get(f"/instances/{test_instance_uuid}.rdf")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/rdf+xml")


def test_get_instance_ntriples(client, db_session):
    add_test_instance(db_session)

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "application/n-triples"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/n-triples")

    response = client.get(f"/instances/{test_instance_uuid}.nt")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/n-triples")


def test_get_instance_turtle(client, db_session):
    add_test_instance(db_session)

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "text/turtle"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/turtle")

    response = client.get(f"/instances/{test_instance_uuid}.ttl")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/turtle")


def test_get_instance_html(client, db_session):
    add_test_instance(db_session)

    # Only a browser (Accept: text/html) on the clean URL gets the HTML view.
    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "text/html"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert "BIBFRAME Instance" in response.text
    # The view links to the alternative RDF serializations.
    assert f"{test_instance_bluecore_uri}.ttl" in response.text

    # An unrecognized format (e.g. `.html`, `.xml`) falls through to the default
    # serialization, which is the HTML view.
    response = client.get(f"/instances/{test_instance_uuid}.html")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")


def test_get_instance_html_names_the_work_by_its_access_point(client, db_session):
    """
    The "Instance of" link names the Work by its access point when it has one.

    This reverses an earlier choice to lead with the title: catalogers compare
    these pages against LC's, where a Work is written as its name/title heading
    ("Author, A. Title"), and the same Work linked from a Hub, an Instance and a
    search result has to read the same in all three. The title is still the
    fallback for records carrying no access point.
    """
    work_uuid = "cd786d58-7adf-4f4e-aa40-3e0560330943"
    work_uri = f"https://bluecore.info/works/{work_uuid}"
    db_session.add(
        Work(
            id=99,
            uuid=work_uuid,
            uri=work_uri,
            data={
                "@id": work_uri,
                "@type": "Work",
                "title": [
                    {
                        "@type": [
                            "VariantTitle",
                            "http://id.loc.gov/vocabulary/vartitletype/por",
                        ],
                        "mainTitle": "One thousand best movies on DVD",
                    },
                    {"@type": "Title", "mainTitle": "REINGESTED 1"},
                ],
                "bflc:aap": "\u00c7evik-Compi\u00e8gne, Burcu. Turkey and India",
            },
        )
    )
    db_session.add(
        Instance(
            id=98,
            uuid=test_instance_uuid,
            uri=str(test_instance_bluecore_uri),
            data=json.loads(orig_graph.serialize(format="json-ld")),
            work_id=99,
        )
    )
    db_session.commit()

    response = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "text/html"}
    )
    assert response.status_code == 200
    assert "Instance of" in response.text
    assert (
        f'<a href="{work_uri}">\u00c7evik-Compi\u00e8gne, Burcu. Turkey and India</a>'
        in response.text
    )
    # the access point stands in for the Work's titles, proper and variant both
    assert "REINGESTED 1" not in response.text
    assert "One thousand best movies on DVD" not in response.text


# cbd requires work & instance and will be tested in test_cbd.py


def test_create_instance(client, derived_from_sparql):
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        format="json-ld",
    )
    payload = {
        "data": original_graph.serialize(format="json-ld"),
        "work_id": None,
    }
    response = client.post("/instances/", headers={"X-User": "cataloger"}, json=payload)
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    new_graph = init_graph()
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT
    new_graph.parse(data=data["data"], format="json-ld")

    assert len(original_graph) != len(new_graph)

    results = new_graph.query(derived_from_sparql)
    derived_from = results.bindings[0]["derived_from"]

    assert str(derived_from).startswith(
        "https://bluecore.info/instances/75d831b9-e0d6-40f0-abb3-e9130622eb8a"
    )

    assert data["uri"].startswith("https://bcld.info/instances"), (
        "Minted URI uses default base url https://bcld.info/"
    )

    # Assert timestamps exist and are identical
    assert "created_at" in data
    assert "updated_at" in data
    assert data["created_at"] == data["updated_at"], (
        "created_at and updated_at should match on creation"
    )


def test_create_instance_without_work_id(client, derived_from_sparql):
    """The editor omits work_id entirely when saving a standalone instance;
    work_id is optional, so this must not 422."""
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        format="json-ld",
    )
    # Note: no "work_id" key at all.
    payload = {"data": original_graph.serialize(format="json-ld")}
    response = client.post("/instances/", headers={"X-User": "cataloger"}, json=payload)
    assert response.status_code == 201


def test_create_instance_with_readonly(client, derived_from_sparql):
    """If a user has both create and cataloger-read-only roles, the read-only role takes precedence and they cannot create an instance."""
    original_graph = init_graph()
    original_graph.parse(
        data=pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
        format="json-ld",
    )
    # Note: no "work_id" key at all.
    payload = {"data": original_graph.serialize(format="json-ld")}
    response = client.post(
        "/instances/", headers={"X-User": "cataloger-conflicting"}, json=payload
    )
    assert response.status_code == 403


def test_update_instance(client, db_session):
    create_response = client.post(
        "/instances/",
        headers={"X-User": "cataloger"},
        json={
            "data": pathlib.Path("tests/blue-core-instance.jsonld").read_text(),
            "work_id": None,
        },
    )
    assert create_response.status_code == 201
    data = create_response.json()
    assert data["data"]["@context"] == CONTEXT_URL
    data["data"]["@context"] = CONTEXT

    instance_uri = rdflib.URIRef(data["uri"])
    instance_uuid = data["uri"].split("/")[-1]
    instance_graph = init_graph()
    instance_graph.parse(data=json.dumps(data["data"]), format="json-ld")

    # Updates Graph: add a LCCN identifier (persisted) and an OCLC number
    # (stripped on save by bluecore_models, see EXCLUDED_TRIPLE_TYPES).
    new_lccn = rdflib.BNode()
    instance_graph.add((instance_uri, BF.identifiedBy, new_lccn))
    instance_graph.add((new_lccn, rdflib.RDF.type, BF.Lccn))
    instance_graph.add((new_lccn, rdflib.RDF.value, rdflib.Literal("2099540000")))

    new_oclc_number = rdflib.BNode()
    instance_graph.add((instance_uri, BF.identifiedBy, new_oclc_number))
    instance_graph.add((new_oclc_number, rdflib.RDF.type, BF.OclcNumber))
    instance_graph.add(
        (new_oclc_number, rdflib.RDF.value, rdflib.Literal("1458303129"))
    )

    put_response = client.put(
        f"/instances/{instance_uuid}",
        headers={"X-User": "cataloger"},
        json={"data": instance_graph.serialize(format="json-ld")},
    )
    assert put_response.status_code == 200
    assert put_response.json()["data"]["@context"] == CONTEXT_URL

    # Retrieve Instance
    get_response = client.get(f"/instances/{instance_uuid}.vnd.sinopia.json")
    payload = get_response.json()
    assert payload["data"]["@context"] == CONTEXT_URL
    payload["data"]["@context"] = CONTEXT
    new_instance_graph = init_graph()
    new_instance_graph.parse(data=json.dumps(payload["data"]), format="json-ld")

    # The newly added LCCN identifier is persisted by the update.
    lccn_values = {
        str(new_instance_graph.value(subject=subject, predicate=rdflib.RDF.value))
        for subject in new_instance_graph.subjects(rdflib.RDF.type, BF.Lccn)
    }
    assert "2099540000" in lccn_values

    # OCLC numbers are stripped on save (EXCLUDED_TRIPLE_TYPES in bluecore_models),
    assert (None, rdflib.RDF.type, BF.OclcNumber) not in new_instance_graph

    # Assert timestamps exist and are now different
    assert "created_at" in payload
    assert "updated_at" in payload
    assert payload["created_at"] != payload["updated_at"], (
        "created_at and updated_at should not match on update"
    )


def test_get_instance_embedding_returns_501(client):
    response = client.get("/instances/some-uuid/embeddings")
    assert response.status_code == 501


def test_create_instance_embedding_returns_501(client):
    response = client.post(
        "/instances/some-uuid/embeddings", headers={"X-User": "cataloger"}
    )
    assert response.status_code == 501


def test_delete_instance(client, db_session):
    add_test_instance(db_session)

    response = client.delete(
        f"/instances/{test_instance_uuid}", headers={"X-User": "cataloger"}
    )
    assert response.status_code == 204

    get_response = client.get(f"/instances/{test_instance_uuid}.vnd.sinopia.json")
    assert get_response.status_code == 404


def test_delete_instance_not_found(client, db_session):
    response = client.delete(
        "/instances/00000000-0000-0000-0000-000000000000",
        headers={"X-User": "cataloger"},
    )
    assert response.status_code == 404


def test_delete_instance_with_other_resources(client, db_session):
    add_test_expanded_instance(db_session)

    response = client.delete(
        f"/instances/{test_expanded_instance_uuid}", headers={"X-User": "cataloger"}
    )
    assert response.status_code == 204

    remaining_links = (
        db_session.query(BibframeOtherResources)
        .filter(BibframeOtherResources.id == 1)
        .first()
    )
    assert remaining_links is None


def test_delete_instance_forbidden(client, db_session):
    add_test_instance(db_session)

    response = client.delete(f"/instances/{test_instance_uuid}")
    assert response.status_code == 403


if __name__ == "__main__":
    pytest.main()


def test_get_instance_html_names_its_work_by_access_point(client, db_session):
    """
    A record reads the same wherever it is linked from. The Work whose Hub page
    calls it "King, Stephen, 1947-. The waste lands" is named that here too,
    not by its bare title.
    """
    from bluecore_models.models import Work

    work_uuid = "68b1dc93-349c-498d-b1f4-98aadd8e7ac8"
    work_uri = f"http://localhost/works/{work_uuid}"
    access_point = "King, Stephen, 1947-. The waste lands"
    work = Work(
        id=71,
        uuid=work_uuid,
        uri=work_uri,
        data={
            "@id": work_uri,
            "@type": "Work",
            "title": {"@type": "Title", "mainTitle": "The waste lands"},
            "bflc:aap": access_point,
        },
    )
    db_session.add(work)
    instance_uuid = "01dd2188-f212-469b-9e72-aa15e1449d72"
    instance_uri = f"http://localhost/instances/{instance_uuid}"
    db_session.add(
        Instance(
            id=72,
            uuid=instance_uuid,
            uri=instance_uri,
            work=work,
            data={
                "@id": instance_uri,
                "@type": "Instance",
                "title": {"@type": "Title", "mainTitle": "The waste lands"},
            },
        )
    )
    db_session.commit()

    response = client.get(
        f"/instances/{instance_uuid}", headers={"Accept": "text/html"}
    )

    assert response.status_code == 200
    assert f'<a href="{work_uri}">{access_point}</a>' in response.text

    # The Instance carries no access point of its own, so the link back to it
    # falls through to its title rather than showing an empty line.
    work_page = client.get(f"/works/{work_uuid}", headers={"Accept": "text/html"})
    assert f'<a href="{instance_uri}">The waste lands</a>' in work_page.text


def test_get_instance_html_dashes_its_list_like_fields(client, db_session):
    """An Instance carries Identified by and Note, and both are dashed."""
    add_test_instance(db_session)

    page = client.get(
        f"/instances/{test_instance_uuid}", headers={"Accept": "text/html"}
    ).text
    fields = dict(re.findall(r"<h2>([^<]+)</h2>(.*?)</div>", page, re.DOTALL))

    assert 'class="bc-bulleted"' in fields["Identified by"]
    for label in ("Title", "Extent"):
        assert 'class="bc-bulleted"' not in fields[label], label
