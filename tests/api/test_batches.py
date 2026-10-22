import json
import re
from pathlib import Path

import pytest
from pymarc import Field, Record, Subfield
from pymarc.field import Indicators
from pytest_httpx import HTTPXMock
from rdflib import RDF, Graph, Namespace

BF = Namespace("http://id.loc.gov/ontologies/bibframe/")

# ------------------------------
# Helpers
# ------------------------------
SIMPLE_XML = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="http://example.org/thing/1">
    <rdf:type rdf:resource="http://example.org/Type"/>
  </rdf:Description>
</rdf:RDF>
"""

SIMPLE_JSONLD = {
    "@context": {"@vocab": "http://example.org/"},
    "@id": "http://example.org/thing/1",
    "@type": "Type",
}


@pytest.mark.asyncio
async def test_create_batch_from_uri(client, httpx_mock: HTTPXMock):
    # mock the call to get the keycloak token for the airflow_workflows client
    httpx_mock.add_response(
        method="POST",
        url=(re.compile(r"^http://airflow:8080/auth/token$")),
        json={"access_token": "xxx"},
    )

    # mock the call to airflow api
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/api/v2/dags/resource_loader/dagRuns$"),
        json={"dag_run_id": "12345"},
    )

    response = client.post(
        "/batches/",
        headers={"X-User": "cataloger"},
        json={"uri": "https://example.com"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["uri"] == "https://example.com"
    assert data["workflow_id"] == "12345"

    # ensure that the http call to airflow included the mocked access token
    assert httpx_mock.get_requests()[1].headers.get("Authorization") == "Bearer xxx"


@pytest.mark.asyncio
async def test_create_batch_from_upload(client, httpx_mock: HTTPXMock):
    # mock the call to get the keycloak token for the airflow_workflows client
    httpx_mock.add_response(
        method="POST",
        url=(re.compile(r"^http://airflow:8080/auth/token$")),
        json={"access_token": "xxx"},
    )

    # mock the call to airflow api
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/api/v2/dags/resource_loader/dagRuns$"),
        json={"dag_run_id": "12345"},
    )

    with open("README.md", "rb") as readme:
        response = client.post(
            "/batches/upload/",
            files={"file": readme},
            headers={"X-User": "cataloger"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["uri"].endswith("README.md")
    assert data["workflow_id"] == "12345"

    # ensure that the http call to airflow included the mocked access token
    assert httpx_mock.get_requests()[1].headers.get("Authorization") == "Bearer xxx"

    # ensure that the file was saved to the uploads directory for airflow
    upload_file = Path("./uploads/") / data["uri"].split("uploads/")[-1]
    assert upload_file.is_file()
    with upload_file.open("r") as saved, open("README.md") as original:
        assert saved.read() == original.read()


def _mock_airflow_chain(httpx_mock: HTTPXMock, dag_run_id="12345"):
    # 1) token
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r"^http://airflow:8080/auth/token$"),
        json={"access_token": "xxx"},
    )
    # 2) create dag run
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/api/v2/dags/resource_loader/dagRuns$"),
        json={"dag_run_id": dag_run_id},
    )


# ------------------------------
# /batches/upload/ (multipart XML)
# ------------------------------
@pytest.mark.asyncio
async def test_upload_multipart_xml_to_jsonld(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _mock_airflow_chain(httpx_mock, dag_run_id="xml-111")

    files = {"file": ("example.xml", SIMPLE_XML, "application/xml")}
    resp = client.post("/batches/upload/", headers={"X-User": "cataloger"}, files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_id"] == "xml-111"
    assert data["uri"].endswith("/example.xml")

    # verify the saved file exists and matches uploaded bytes
    saved_rel = data["uri"].split("uploads/")[-1]
    saved_path = Path("./uploads") / saved_rel
    assert saved_path.is_file()
    assert saved_path.read_bytes() == SIMPLE_XML

    # Airflow call should have Authorization header
    assert httpx_mock.get_requests()[1].headers.get("Authorization") == "Bearer xxx"


# ------------------------------
# /batches/upload/ (multipart JSON-LD passthrough)
# ------------------------------
@pytest.mark.asyncio
async def test_upload_multipart_jsonld_passthrough(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _mock_airflow_chain(httpx_mock, dag_run_id="jsonld-222")

    body = json.dumps(SIMPLE_JSONLD).encode("utf-8")
    files = {"file": ("graph.jsonld", body, "application/ld+json")}
    resp = client.post("/batches/upload/", headers={"X-User": "cataloger"}, files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_id"] == "jsonld-222"
    assert data["uri"].endswith(".jsonld")

    saved_rel = data["uri"].split("uploads/")[-1]
    saved_path = Path("./uploads") / saved_rel
    assert saved_path.is_file()
    assert json.loads(saved_path.read_text()) == SIMPLE_JSONLD

    assert httpx_mock.get_requests()[1].headers.get("Authorization") == "Bearer xxx"


# ------------------------------
# /batches/upload/ (raw XML body)
# ------------------------------
@pytest.mark.asyncio
async def test_upload_raw_xml_body(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _mock_airflow_chain(httpx_mock, dag_run_id="raw-444")

    resp = client.post(
        "/batches/upload/",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=SIMPLE_XML,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_id"] == "raw-444"
    assert data["uri"].endswith(".jsonld")

    saved_rel = data["uri"].split("uploads/")[-1]
    saved_path = Path("./uploads") / saved_rel
    assert saved_path.is_file()
    json.loads(saved_path.read_text())


# ------------------------------
# /batches/upload/ (archive -> archived_file_loader DAG)
# ------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["records.zip", "records.tar.gz", "records.tgz"])
async def test_upload_archive_routes_to_archive_loader(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path, filename
):
    monkeypatch.chdir(tmp_path)
    # token
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r"^http://airflow:8080/auth/token$"),
        json={"access_token": "xxx"},
    )
    # archive uploads should trigger the archived_file_loader DAG, not resource_loader
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/api/v2/dags/archived_file_loader/dagRuns$"),
        json={"dag_run_id": "archive-999"},
    )

    files = {"file": (filename, b"not-a-real-archive", "application/octet-stream")}
    resp = client.post("/batches/upload/", headers={"X-User": "cataloger"}, files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_id"] == "archive-999"
    assert data["uri"].endswith(f"/{filename}")

    # the file is passed through as-is for the DAG to unpack
    saved_rel = data["uri"].split("uploads/")[-1]
    saved_path = Path("./uploads") / saved_rel
    assert saved_path.is_file()
    assert saved_path.read_bytes() == b"not-a-real-archive"


# ------------------------------
# Error cases
# ------------------------------
@pytest.mark.asyncio
async def test_upload_plain_text_passthrough(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _mock_airflow_chain(httpx_mock, dag_run_id="txt-555")

    files = {"file": ("notes.txt", b"hello", "text/plain")}
    resp = client.post("/batches/upload/", headers={"X-User": "cataloger"}, files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_id"] == "txt-555"
    assert data["uri"].endswith("/notes.txt")

    saved_rel = data["uri"].split("uploads/")[-1]
    saved_path = Path("./uploads") / saved_rel
    assert saved_path.is_file()
    assert saved_path.read_bytes() == b"hello"
    assert httpx_mock.get_requests()[1].headers.get("Authorization") == "Bearer xxx"


# JSON missing 'rdfxml': returns 422 BEFORE Airflow call
@pytest.mark.asyncio
async def test_upload_json_body_missing_rdfxml(client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    payload = {"name": "missing"}
    resp = client.post(
        "/batches/upload/",
        headers={"X-User": "cataloger", "Content-Type": "application/json"},
        json=payload,
    )
    assert resp.status_code == 422
    assert "Provide 'rdfxml' in the JSON body" in resp.text


# ------------------------------
# /batches/upload/ (MARC -> BIBFRAME JSON-LD -> resource_loader)
# ------------------------------
def _marc_bytes(*titles: str) -> bytes:
    """Binary MARC21, one record per title, each with its own 001."""
    records = []
    for number, title in enumerate(titles, start=1):
        record = Record()
        record.add_field(Field(tag="001", data=f"rec{number}"))
        record.add_field(
            Field(
                tag="245",
                indicators=Indicators("1", "0"),
                subfields=[Subfield("a", title)],
            )
        )
        records.append(record.as_marc())
    return b"".join(records)


MARCXML_TWO_RECORDS = b"""<?xml version="1.0" encoding="UTF-8"?>
<collection xmlns="http://www.loc.gov/MARC21/slim">
  <record>
    <leader>01142cam a2200301 a 4500</leader>
    <controlfield tag="001">111</controlfield>
    <controlfield tag="008">920219s1993    caua          001 0 eng  </controlfield>
    <datafield tag="245" ind1="1" ind2="0"><subfield code="a">Title A</subfield></datafield>
  </record>
  <record>
    <leader>01142cam a2200301 a 4500</leader>
    <controlfield tag="001">222</controlfield>
    <controlfield tag="008">920219s1994    caua          001 0 eng  </controlfield>
    <datafield tag="245" ind1="1" ind2="0"><subfield code="a">Title B</subfield></datafield>
  </record>
</collection>"""


def _saved_graph(data: dict) -> Graph:
    """Parse the file the upload handed Airflow, as resource_loader would."""
    assert data["uri"].endswith(".jsonld")
    saved_path = Path("./uploads") / data["uri"].split("uploads/")[-1]
    return Graph().parse(saved_path, format="json-ld")


def _titles(graph: Graph) -> set[str]:
    return {str(o) for o in graph.objects(None, BF.mainTitle)}


def _airflow_conf(httpx_mock: HTTPXMock) -> dict:
    return json.loads(httpx_mock.get_requests()[1].content)["conf"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename,content_type",
    [
        ("records.mrc", "application/octet-stream"),
        ("RECORDS.MARC", "application/octet-stream"),
        ("export.bin", "application/marc"),
    ],
)
async def test_upload_multipart_marc_converts_every_record(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path, filename, content_type
):
    monkeypatch.chdir(tmp_path)
    _mock_airflow_chain(httpx_mock, dag_run_id="marc-1")

    files = {"file": (filename, _marc_bytes("Title A", "Title B"), content_type)}
    resp = client.post("/batches/upload/", headers={"X-User": "cataloger"}, files=files)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["workflow_id"] == "marc-1"
    # every record in the file, not just the first: this is the bulk path
    assert _titles(_saved_graph(data)) == {"Title A", "Title B"}
    # what resource_loader is handed is the converted JSON-LD, not the MARC
    assert _airflow_conf(httpx_mock)["file"] == data["uri"]


@pytest.mark.asyncio
async def test_upload_raw_marc_body(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _mock_airflow_chain(httpx_mock, dag_run_id="marc-2")

    resp = client.post(
        "/batches/upload/",
        headers={"X-User": "cataloger", "Content-Type": "application/marc"},
        content=_marc_bytes("Title A", "Title B", "Title C"),
    )

    assert resp.status_code == 200, resp.text
    assert _titles(_saved_graph(resp.json())) == {"Title A", "Title B", "Title C"}


@pytest.mark.asyncio
async def test_upload_raw_marcxml_body_is_read_as_marc_not_rdfxml(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _mock_airflow_chain(httpx_mock, dag_run_id="marc-3")

    resp = client.post(
        "/batches/upload/",
        headers={"X-User": "cataloger", "Content-Type": "application/xml"},
        content=MARCXML_TWO_RECORDS,
    )

    assert resp.status_code == 200, resp.text
    assert _titles(_saved_graph(resp.json())) == {"Title A", "Title B"}


@pytest.mark.asyncio
async def test_upload_marc_matches_marc2bibframe(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    """Both routes into Blue Core must agree, Blue Core policy included."""
    monkeypatch.chdir(tmp_path)
    _mock_airflow_chain(httpx_mock, dag_run_id="marc-4")
    marc = _marc_bytes("Title A")
    base = "https://example.edu/catalog/"

    upload = client.post(
        f"/batches/upload/?source_base_uri={base}",
        headers={"X-User": "cataloger"},
        files={"file": ("one.mrc", marc, "application/octet-stream")},
    )
    converted = client.post(
        f"/marc2bibframe?source_base_uri={base}",
        headers={"X-User": "cataloger", "Content-Type": "application/marc"},
        content=marc,
    )

    assert upload.status_code == 200, upload.text
    assert converted.status_code == 200, converted.text
    ingested = _saved_graph(upload.json())
    expected = Graph().parse(data=converted.text, format="json-ld")
    # Compare the minted subjects rather than whole graphs: the transform
    # stamps a generation time, and blank nodes differ from run to run.
    assert set(ingested.subjects(RDF.type, BF.Work)) == set(
        expected.subjects(RDF.type, BF.Work)
    )
    assert any(str(s).startswith(base) for s in ingested.subjects(RDF.type, BF.Work))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [b"", b"this is not MARC"], ids=["empty", "unreadable"]
)
async def test_upload_bad_marc_is_422_without_starting_a_dag(
    client, monkeypatch, tmp_path, body
):
    """No Airflow call is mocked, so pytest-httpx fails the test if one is made."""
    monkeypatch.chdir(tmp_path)

    resp = client.post(
        "/batches/upload/",
        headers={"X-User": "cataloger"},
        files={"file": ("bad.mrc", body, "application/octet-stream")},
    )

    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_upload_marc_rejects_a_bad_source_base_uri(client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    resp = client.post(
        "/batches/upload/?source_base_uri=not-a-uri",
        headers={"X-User": "cataloger"},
        files={"file": ("one.mrc", _marc_bytes("Title A"), "application/marc")},
    )

    assert resp.status_code == 422
    assert "source_base_uri" in resp.text
