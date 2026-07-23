import pytest
from pymarc import Field, Record, Subfield


def _make_marc_bytes() -> bytes:
    """Return a minimal binary MARC21 record as bytes."""
    record = Record()
    record.add_field(
        Field(tag="245", indicators=["1", "0"], subfields=[Subfield("a", "Test title")])
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
        Field(tag="245", indicators=["1", "0"], subfields=[Subfield("a", "Title A")])
    )
    record_b = Record()
    record_b.add_field(
        Field(tag="245", indicators=["1", "0"], subfields=[Subfield("a", "Title B")])
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
async def test_marc2bibframe_unsupported_content_type_returns_415(client):
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/marc"},
        content=MARCXML,
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_marc2bibframe_invalid_xml_returns_422(client):
    resp = client.post(
        "/marc2bibframe",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=b"this is not xml at all!!",
    )
    assert resp.status_code == 422
