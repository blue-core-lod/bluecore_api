import pytest
from pymarc import Field, Record, Subfield
from pymarc.field import Indicators
from rdflib import Graph, URIRef


def _make_marc_bytes() -> bytes:
    """Return a minimal binary MARC21 record as bytes."""
    record = Record()
    record.add_field(
        Field(
            tag="245",
            indicators=Indicators("1", "0"),
            subfields=[Subfield("a", "Test title")],
        )
    )
    return record.as_marc()


MARC_BYTES = _make_marc_bytes()

# Minimal MARCXML with enough fields for a successful bibframe conversion.
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


# ---------------------------------------------------------------------------
# POST /marc2xml — multipart file upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marc2xml_multipart(client):
    resp = client.post(
        "/marc2xml",
        files={"file": ("test.mrc", MARC_BYTES, "application/marc")},
        headers={"X-User": "cataloger"},
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    body = resp.text
    assert "<collection" in body
    assert "Test title" in body
    assert "<record>" in body


# ---------------------------------------------------------------------------
# POST /marc2xml — raw binary body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marc2xml_raw_body(client):
    resp = client.post(
        "/marc2xml",
        headers={"X-User": "cataloger", "Content-Type": "application/marc"},
        content=MARC_BYTES,
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    body = resp.text
    assert "<collection" in body
    assert "Test title" in body


# ---------------------------------------------------------------------------
# POST /marc2xml — multiple records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marc2xml_multiple_records(client):
    record_a = Record()
    record_a.add_field(
        Field(
            tag="245",
            indicators=Indicators("1", "0"),
            subfields=[Subfield("a", "Title A")],
        )
    )
    record_b = Record()
    record_b.add_field(
        Field(
            tag="245",
            indicators=Indicators("1", "0"),
            subfields=[Subfield("a", "Title B")],
        )
    )
    multi_marc = record_a.as_marc() + record_b.as_marc()

    resp = client.post(
        "/marc2xml",
        files={"file": ("multi.mrc", multi_marc, "application/marc")},
        headers={"X-User": "cataloger"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert body.count("<record>") == 2
    assert "Title A" in body
    assert "Title B" in body


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marc2xml_empty_body_returns_422(client):
    resp = client.post(
        "/marc2xml",
        headers={"X-User": "cataloger", "Content-Type": "application/marc"},
        content=b"",
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_marc2xml_unsupported_content_type_returns_415(client):
    resp = client.post(
        "/marc2xml",
        headers={"X-User": "cataloger", "Content-Type": "text/plain"},
        content=b"not marc",
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_marc2xml_invalid_marc_returns_422(client):
    resp = client.post(
        "/marc2xml",
        headers={"X-User": "cataloger", "Content-Type": "application/marc"},
        content=b"this is not valid marc data at all!!",
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /marc2bibframe — multipart file upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marc2bibframe_multipart(client):
    resp = client.post(
        "/marc2bibframe",
        files={"file": ("test.xml", MARCXML, "application/xml")},
        headers={"X-User": "cataloger"},
    )
    assert resp.status_code == 200
    assert "ld+json" in resp.headers["content-type"]
    data = resp.json()
    assert isinstance(data, list)
    types = {t for node in data for t in (node.get("@type") or [])}
    assert any("Work" in t for t in types)


# ---------------------------------------------------------------------------
# POST /marc2bibframe — raw XML body (application/xml)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marc2bibframe_raw_application_xml(client):
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=MARCXML,
    )
    assert resp.status_code == 200
    assert "ld+json" in resp.headers["content-type"]
    data = resp.json()
    assert isinstance(data, list)
    types = {t for node in data for t in (node.get("@type") or [])}
    assert any("Work" in t for t in types)


# ---------------------------------------------------------------------------
# POST /marc2bibframe — raw XML body (text/xml)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marc2bibframe_raw_text_xml(client):
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "text/xml"},
        content=MARCXML,
    )
    assert resp.status_code == 200
    assert "ld+json" in resp.headers["content-type"]
    data = resp.json()
    assert isinstance(data, list)
    types = {t for node in data for t in (node.get("@type") or [])}
    assert any("Instance" in t for t in types)


# ---------------------------------------------------------------------------
# POST /marc2bibframe — error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marc2bibframe_empty_body_returns_422(client):
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=b"",
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_marc2bibframe_with_binary_marc_returns_200(client):
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/marc"},
        content=MARC_BYTES,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_marc2bibframe_invalid_xml_returns_422(client):
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=b"this is not xml at all!!",
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /marc2bibframe — Blue Core policy
# ---------------------------------------------------------------------------

DLC = "http://id.loc.gov/vocabulary/organizations/dlc"
CBC = "http://id.loc.gov/vocabulary/organizations/cbc"
ASSIGNER = "http://id.loc.gov/ontologies/bibframe/assigner"


@pytest.mark.asyncio
async def test_marc2bibframe_rewrites_the_dlc_assigner_to_cbc(client):
    """Blue Core records are assigned by CBC, whatever the MARC says.

    The bluecore-workflows marc2bf DAG applies the same rewrite, so the two
    routes into Blue Core agree.
    """
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=MARCXML,
    )
    assert resp.status_code == 200

    assigners = {
        ref.get("@id") for node in resp.json() for ref in (node.get(ASSIGNER) or [])
    }
    assert CBC in assigners
    assert DLC not in assigners


# ---------------------------------------------------------------------------
# POST /marc2bibframe — Accept negotiation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "accept,expected_content_type,rdflib_format",
    [
        ("application/ld+json", "application/ld+json", "json-ld"),
        ("application/rdf+xml", "application/rdf+xml", "xml"),
        ("text/turtle", "text/turtle", "turtle"),
        ("application/n-triples", "application/n-triples", "nt"),
    ],
)
@pytest.mark.asyncio
async def test_marc2bibframe_serializes_what_accept_asks_for(
    client, accept, expected_content_type, rdflib_format
):
    resp = client.post(
        "/marc2bibframe",
        headers={
            "X-User": "cataloger",
            "Content-Type": "application/xml",
            "Accept": accept,
        },
        content=MARCXML,
    )
    assert resp.status_code == 200
    assert expected_content_type in resp.headers["content-type"]
    # The body really is that serialization, not just labelled as it.
    graph = Graph()
    graph.parse(data=resp.text, format=rdflib_format)
    assert len(graph) > 0


@pytest.mark.parametrize("accept", [None, "*/*", "application/*", "application/json"])
@pytest.mark.asyncio
async def test_marc2bibframe_defaults_to_jsonld(client, accept):
    """Clients that predate negotiation must keep getting JSON-LD.

    sinopia_editor's fetch sends no explicit Accept, which reaches us as */*;
    bluecore-client asks for application/ld+json.
    """
    headers = {"X-User": "cataloger", "Content-Type": "application/xml"}
    if accept is not None:
        headers["Accept"] = accept

    resp = client.post("/marc2bibframe", headers=headers, content=MARCXML)
    assert resp.status_code == 200
    assert "ld+json" in resp.headers["content-type"]
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_marc2bibframe_unsupported_accept_returns_406(client):
    resp = client.post(
        "/marc2bibframe",
        headers={
            "X-User": "cataloger",
            "Content-Type": "application/xml",
            "Accept": "text/csv",
        },
        content=MARCXML,
    )
    assert resp.status_code == 406
    assert "text/turtle" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_marc2bibframe_wildcard_after_unsupported_type_still_works(client):
    """A browser-style Accept list is satisfied by its trailing wildcard."""
    resp = client.post(
        "/marc2bibframe",
        headers={
            "X-User": "cataloger",
            "Content-Type": "application/xml",
            "Accept": "text/csv, */*;q=0.8",
        },
        content=MARCXML,
    )
    assert resp.status_code == 200
    assert "ld+json" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_marc2bibframe_honors_accept_quality_order_not_weights(client):
    """Matching follows header order, as app/utils/serializer.serialize() does."""
    resp = client.post(
        "/marc2bibframe",
        headers={
            "X-User": "cataloger",
            "Content-Type": "application/xml",
            "Accept": "text/turtle;q=0.1, application/rdf+xml;q=0.9",
        },
        content=MARCXML,
    )
    assert resp.status_code == 200
    assert "text/turtle" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_marc2bibframe_applies_blue_core_policy_in_every_serialization(client):
    """The DLC->CBC rewrite is not a quirk of the JSON-LD path."""
    resp = client.post(
        "/marc2bibframe",
        headers={
            "X-User": "cataloger",
            "Content-Type": "application/xml",
            "Accept": "text/turtle",
        },
        content=MARCXML,
    )
    assert resp.status_code == 200

    graph = Graph()
    graph.parse(data=resp.text, format="turtle")
    assigners = {str(o) for o in graph.objects(predicate=URIRef(ASSIGNER))}
    assert CBC in assigners
    # Note the rewrite retargets the bf:assigner triple; the DLC agent node
    # itself is left in the graph, so assert on the property, not the text.
    assert DLC not in assigners


# ---------------------------------------------------------------------------
# POST /marc2bibframe — source_base_uri
# ---------------------------------------------------------------------------


def _minted_subjects(body: str, prefix: str) -> set[str]:
    graph = Graph()
    graph.parse(data=body, format="turtle")
    return {str(s) for s in graph.subjects() if str(s).startswith(prefix)}


def _post_for_turtle(client, params: str = "") -> str:
    resp = client.post(
        f"/marc2bibframe{params}",
        headers={
            "X-User": "cataloger",
            "Content-Type": "application/xml",
            "Accept": "text/turtle",
        },
        content=MARCXML,
    )
    assert resp.status_code == 200
    return resp.text


@pytest.mark.asyncio
async def test_marc2bibframe_default_source_base_uri_matches_the_dag(client):
    """Unasked, the endpoint mints under the marc_to_bibframe DAG's base."""
    minted = _minted_subjects(_post_for_turtle(client), "http://id.loc.gov/resources/")
    assert "http://id.loc.gov/resources/92005291#Work" in minted
    assert "http://id.loc.gov/resources/92005291#Instance" in minted


@pytest.mark.asyncio
async def test_marc2bibframe_honors_source_base_uri(client):
    body = _post_for_turtle(client, "?source_base_uri=https://example.edu/catalog/")
    assert "https://example.edu/catalog/92005291#Work" in _minted_subjects(
        body, "https://example.edu/catalog/"
    )
    assert "id.loc.gov/resources/92005291" not in body


@pytest.mark.asyncio
async def test_marc2bibframe_adds_a_missing_trailing_delimiter(client):
    """The transform concatenates base and record id, so a bare base would
    otherwise mint https://example.edu/catalog92005291#Work."""
    with_slash = _post_for_turtle(
        client, "?source_base_uri=https://example.edu/catalog/"
    )
    without_slash = _post_for_turtle(
        client, "?source_base_uri=https://example.edu/catalog"
    )
    assert _minted_subjects(
        without_slash, "https://example.edu/catalog"
    ) == _minted_subjects(with_slash, "https://example.edu/catalog")
    assert "catalog92005291" not in without_slash
