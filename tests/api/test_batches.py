import json
import re
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock


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
# /batches/ (URI variant)
# ------------------------------
@pytest.mark.asyncio
async def test_create_batch_from_uri(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    # ensure uploads happen under tmp working dir
    monkeypatch.chdir(tmp_path)

    _mock_airflow_chain(httpx_mock, dag_run_id="12345")

    resp = client.post(
        "/batches/",
        headers={"X-User": "cataloger"},
        json={"uri": "https://example.com/data.jsonld"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["uri"] == "https://example.com/data.jsonld"
    assert data["workflow_id"] == "12345"

    # Airflow call should have Authorization header
    assert httpx_mock.get_requests()[1].headers.get("Authorization") == "Bearer xxx"


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
    assert data["uri"].endswith(".jsonld")

    # Verify file exists and is valid JSON
    jsonld_rel = data["uri"].split("uploads/")[-1]  # everything after 'uploads/'
    jsonld_path = Path("./uploads") / jsonld_rel
    assert jsonld_path.is_file()
    # rdflib wrote JSON-LD text; ensure it's JSON
    json.loads(jsonld_path.read_text())

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
# /batches/upload/ (application/json body with rdfxml)
# ------------------------------
@pytest.mark.asyncio
async def test_upload_json_body_with_rdfxml(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _mock_airflow_chain(httpx_mock, dag_run_id="json-333")

    payload = {"name": "from_json", "rdfxml": SIMPLE_XML.decode("utf-8")}
    resp = client.post(
        "/batches/upload/",
        headers={"X-User": "cataloger", "Content-Type": "application/json"},
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_id"] == "json-333"
    assert data["uri"].endswith(".jsonld")

    saved_rel = data["uri"].split("uploads/")[-1]
    saved_path = Path("./uploads") / saved_rel
    assert saved_path.is_file()
    json.loads(saved_path.read_text())


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
        content=SIMPLE_XML,  # Starlette TestClient uses 'content' for raw bytes
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
# Error cases
# ------------------------------
@pytest.mark.asyncio
async def test_upload_unsupported_file_type(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    # We still mock to avoid accidental network calls even though this should 415 before calling Airflow.
    _mock_airflow_chain(httpx_mock, dag_run_id="nope-555")

    files = {"file": ("notes.txt", b"hello", "text/plain")}
    resp = client.post("/batches/upload/", headers={"X-User": "cataloger"}, files=files)
    assert resp.status_code == 415
    assert "Unsupported file type" in resp.text


@pytest.mark.asyncio
async def test_upload_json_body_missing_rdfxml(
    client, httpx_mock: HTTPXMock, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _mock_airflow_chain(httpx_mock, dag_run_id="nope-666")

    # Missing rdfxml key
    payload = {"name": "missing"}
    resp = client.post(
        "/batches/upload/",
        headers={"X-User": "cataloger", "Content-Type": "application/json"},
        json=payload,
    )
    assert resp.status_code == 422
    assert "Provide 'rdfxml' in the JSON body" in resp.text
