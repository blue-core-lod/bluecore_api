import pytest
from pymarc import Field, Record, Subfield
from pymarc.field import Indicators
from rdflib import RDF, Graph, URIRef
from rdflib.compare import isomorphic

from bluecore_api.app.routes import convert


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


# A collection of two records, for the multi-record cases below.
MARCXML_TWO_RECORDS = b"""<?xml version="1.0" encoding="UTF-8"?>
<collection xmlns="http://www.loc.gov/MARC21/slim">
  <record>
    <leader>01142cam a2200301 a 4500</leader>
    <controlfield tag="001">111</controlfield>
    <controlfield tag="008">920219s1993    caua          001 0 eng  </controlfield>
    <datafield tag="245" ind1="1" ind2="0">
      <subfield code="a">Title A /</subfield>
    </datafield>
  </record>
  <record>
    <leader>01142cam a2200301 a 4500</leader>
    <controlfield tag="001">222</controlfield>
    <controlfield tag="008">920219s1994    caua          001 0 eng  </controlfield>
    <datafield tag="245" ind1="1" ind2="0">
      <subfield code="a">Title B /</subfield>
    </datafield>
  </record>
</collection>"""


def _make_multi_marc_bytes() -> bytes:
    """Two binary MARC21 records with distinct 001s."""
    records = []
    for control_number, title in (("111", "Title A"), ("222", "Title B")):
        record = Record()
        record.add_field(Field(tag="001", data=control_number))
        record.add_field(
            Field(
                tag="245",
                indicators=Indicators("1", "0"),
                subfields=[Subfield("a", title)],
            )
        )
        records.append(record.as_marc())
    return b"".join(records)


MULTI_MARC_BYTES = _make_multi_marc_bytes()


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


# ---------------------------------------------------------------------------
# One record per request
#
# These routes convert one record and refuse anything else with a 413 (see the
# module docstring in app/routes/convert.py). Load testing with real Library of
# Congress records found a thousand-record upload stalling every endpoint for
# 9.5 s, because the transform runs on the event loop and production has a
# single worker.
# ---------------------------------------------------------------------------

BF_WORK = URIRef("http://id.loc.gov/ontologies/bibframe/Work")
BF_INSTANCE = URIRef("http://id.loc.gov/ontologies/bibframe/Instance")
BF_MAIN_TITLE = URIRef("http://id.loc.gov/ontologies/bibframe/mainTitle")


@pytest.mark.parametrize("path", ["/marc2xml", "/marc2bibframe"])
@pytest.mark.asyncio
async def test_multiple_binary_records_rejected(client, path):
    resp = client.post(
        path,
        headers={"X-User": "cataloger", "Content-Type": "application/marc"},
        content=MULTI_MARC_BYTES,
    )
    assert resp.status_code == 413
    assert "2 records" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_multiple_binary_records_rejected_via_multipart(client):
    resp = client.post(
        "/marc2xml",
        files={"file": ("multi.mrc", MULTI_MARC_BYTES, "application/marc")},
        headers={"X-User": "cataloger"},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_marcxml_collection_of_several_rejected(client):
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=MARCXML_TWO_RECORDS,
    )
    assert resp.status_code == 413
    assert "2 records" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_namespace_prefixed_collection_is_counted(client):
    """A byte scan for b"<record" would miss these and let the batch through."""
    prefixed = (
        MARCXML_TWO_RECORDS.replace(b"<record", b"<marc:record")
        .replace(b"</record>", b"</marc:record>")
        .replace(
            b'<collection xmlns="http://www.loc.gov/MARC21/slim">',
            b'<marc:collection xmlns:marc="http://www.loc.gov/MARC21/slim">',
        )
        .replace(b"</collection>", b"</marc:collection>")
    )

    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=prefixed,
    )
    assert resp.status_code == 413
    assert "2 records" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_multiple_records_without_control_numbers_rejected(client):
    """The no-001 path still counts, though the records get synthesized ids."""
    records = []
    for title in ("Title A", "Title B"):
        record = Record()
        record.add_field(
            Field(
                tag="245",
                indicators=Indicators("1", "0"),
                subfields=[Subfield("a", title)],
            )
        )
        records.append(record.as_marc())

    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/marc"},
        content=b"".join(records),
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_bare_record_without_a_collection_wrapper_converts(client):
    """A single <record> with no <collection> around it is still one record."""
    bare = (
        b'<record xmlns="http://www.loc.gov/MARC21/slim">'
        b"<leader>01142cam a2200301 a 4500</leader>"
        b'<controlfield tag="001">999</controlfield>'
        b'<datafield tag="245" ind1="1" ind2="0">'
        b'<subfield code="a">Bare record /</subfield>'
        b"</datafield></record>"
    )
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=bare,
    )
    assert resp.status_code == 200
    graph = Graph()
    graph.parse(data=resp.text, format="json-ld")
    assert (
        URIRef("http://id.loc.gov/resources/999#Work"),
        RDF.type,
        BF_WORK,
    ) in graph


# ---------------------------------------------------------------------------
# Byte limit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/marc2xml", "/marc2bibframe"])
@pytest.mark.asyncio
async def test_oversized_body_rejected(client, monkeypatch, path):
    """Patched rather than sending a real megabyte, to keep the suite quick."""
    monkeypatch.setattr(convert, "MAX_CONVERT_BYTES", 10)
    resp = client.post(
        path,
        headers={"X-User": "cataloger", "Content-Type": "application/marc"},
        content=MARC_BYTES,
    )
    assert resp.status_code == 413
    assert "at most 10" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_oversized_body_rejected_before_it_is_read(client, monkeypatch):
    """TestClient sets Content-Length, so the pre-read check fires first.

    Distinguished from the post-read check by its wording: this one quotes the
    declared length rather than the number of bytes actually read.
    """
    monkeypatch.setattr(convert, "MAX_CONVERT_BYTES", 10)
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=MARCXML,
    )
    assert resp.status_code == 413
    assert f"Body is {len(MARCXML)} bytes" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Byte order mark
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marcxml_with_a_utf8_bom_converts(client):
    """A BOM used to send valid MARCXML down the binary MARC path.

    Windows editors add one invisibly, and bytes.lstrip() does not remove it, so
    the "starts with '<'" sniff saw EF BB BF and guessed wrong. Found by load
    testing a real LC record saved as MARCXML on Windows.
    """
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=b"\xef\xbb\xbf" + MARCXML,
    )
    assert resp.status_code == 200

    without_bom = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=MARCXML,
    )
    # Compared as graphs, not as JSON: rdflib mints fresh blank node labels on
    # every run, so the two serializations differ even when the RDF matches.
    assert isomorphic(
        Graph().parse(data=resp.text, format="json-ld"),
        Graph().parse(data=without_bom.text, format="json-ld"),
    )


@pytest.mark.asyncio
async def test_marcxml_with_a_bom_converts_via_multipart(client):
    resp = client.post(
        "/marc2bibframe",
        files={"file": ("bom.xml", b"\xef\xbb\xbf" + MARCXML, "application/xml")},
        headers={"X-User": "cataloger"},
    )
    assert resp.status_code == 200
