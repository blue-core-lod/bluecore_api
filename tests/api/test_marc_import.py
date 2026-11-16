"""The editor's MARC import: convert with /marc2bibframe, then POST the result.

The conversion mints placeholder URIs under http://example.org/ for the Work
and Instance. Those name nothing, so an import passes record_derived_from=false
and the save mints Blue Core URIs without recording the placeholders as
bf:derivedFrom (sinopia_editor#271).
"""

import json

import pytest
from bluecore_models.models import Instance, Work

CATALOGER = {"X-User": "cataloger"}

MARCXML = b"""<?xml version="1.0" encoding="UTF-8"?>
<collection xmlns="http://www.loc.gov/MARC21/slim">
  <record>
    <leader>01142cam a2200301 a 4500</leader>
    <controlfield tag="001">   92005291 </controlfield>
    <controlfield tag="003">DLC</controlfield>
    <controlfield tag="008">920219s1993    caua          001 0 eng  </controlfield>
    <datafield tag="245" ind1="1" ind2="0">
      <subfield code="a">Getting started with Marc /</subfield>
      <subfield code="c">John Doe.</subfield>
    </datafield>
    <datafield tag="100" ind1="1" ind2=" ">
      <subfield code="a">Doe, John,</subfield>
      <subfield code="d">1950-</subfield>
    </datafield>
  </record>
</collection>"""


def _converted(client) -> str:
    resp = client.post(
        "/marc2bibframe",
        headers={**CATALOGER, "Content-Type": "application/xml"},
        content=MARCXML,
    )
    assert resp.status_code == 200
    assert "http://example.org/92005291#Work" in resp.text
    return resp.text


def _derived_from(data) -> list[str]:
    """The @id of every bf:derivedFrom anywhere in a record's JSON-LD.

    A value is a bare node or a list of them, depending on how it was framed.
    """
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "derivedFrom":
                nodes = value if isinstance(value, list) else [value]
                found.extend(node["@id"] for node in nodes)
            found.extend(_derived_from(value))
    elif isinstance(data, list):
        for item in data:
            found.extend(_derived_from(item))
    return found


@pytest.mark.parametrize("route", ["/works/", "/instances/"])
def test_record_derived_from_is_documented_as_an_optional_query_param(client, route):
    operation = client.get("/openapi.json").json()["paths"][route]["post"]
    param = next(
        p for p in operation["parameters"] if p["name"] == "record_derived_from"
    )
    assert param["in"] == "query"
    assert param["required"] is False
    assert param["schema"]["default"] is True


def test_marc_import_as_a_work_records_no_derived_from(client, db_session):
    resp = client.post(
        "/works/?record_derived_from=false",
        headers=CATALOGER,
        json={"data": _converted(client)},
    )

    assert resp.status_code == 201
    work = resp.json()
    assert work["uri"].startswith("https://bcld.info/works/")
    assert work["data"]["adminMetadata"], "admin metadata is still generated"
    assert _derived_from(work["data"]) == []

    # The Instance the record describes is saved too, without one either.
    saved = db_session.query(Work).filter(Work.uri == work["uri"]).one()
    assert saved.instances, "the import's Instance is saved as its own record"
    for instance in saved.instances:
        assert instance.uri.startswith("https://bcld.info/instances/")
        assert _derived_from(instance.data) == []


def test_marc_import_as_an_instance_records_no_derived_from(client, db_session):
    resp = client.post(
        "/instances/?record_derived_from=false",
        headers=CATALOGER,
        json={"data": _converted(client)},
    )

    assert resp.status_code == 201
    instance = resp.json()
    assert instance["uri"].startswith("https://bcld.info/instances/")
    assert _derived_from(instance["data"]) == []

    saved = db_session.query(Instance).filter(Instance.uri == instance["uri"]).one()
    assert saved.work is not None
    assert _derived_from(saved.work.data) == []


def test_marc_import_records_derived_from_by_default(client, db_session):
    """Callers that don't ask keep today's behavior: the bulk loader and the
    workflows rely on derivedFrom to find a record they have loaded before."""
    resp = client.post("/works/", headers=CATALOGER, json={"data": _converted(client)})

    assert resp.status_code == 201
    assert _derived_from(resp.json()["data"]) == ["http://example.org/92005291#Work"]


def test_record_derived_from_rejects_a_non_boolean(client, db_session):
    resp = client.post(
        "/works/?record_derived_from=sometimes",
        headers=CATALOGER,
        json={
            "data": json.dumps({"@type": "http://id.loc.gov/ontologies/bibframe/Work"})
        },
    )
    assert resp.status_code == 422
