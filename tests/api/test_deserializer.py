import json

import pytest
from bluecore_models.utils.graph import CONTEXT
from bluecore_models.utils.graph import CONTEXT_URL as BIBFRAME_CONTEXT_URL
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from bluecore_api.app.utils.deserializer import (
    JSONLD_CONTENT_TYPE,
    RDFXML_CONTENT_TYPE,
    deserialize,
)
from bluecore_api.constants import CONTEXT_URL


class RequiredFieldSchema(BaseModel):
    data: str
    required: str


class DataOnlySchema(BaseModel):
    data: str


def request_with_body(body: bytes, content_type: str) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-type", content_type.encode())],
        },
        receive,
    )


@pytest.mark.asyncio
async def test_deserialize_jsonld_wraps_body_as_data():
    request = request_with_body(
        json.dumps({"@id": "https://example.com/resource"}).encode(),
        JSONLD_CONTENT_TYPE,
    )

    parsed = await deserialize(DataOnlySchema)(request)

    assert json.loads(parsed.data) == {"@id": "https://example.com/resource"}


@pytest.mark.asyncio
async def test_deserialize_invalid_json_raises_unprocessable_entity():
    request = request_with_body(b"{", JSONLD_CONTENT_TYPE)

    with pytest.raises(HTTPException) as error:
        await deserialize(DataOnlySchema)(request)

    assert error.value.status_code == 422
    assert "Invalid JSON body" in error.value.detail


@pytest.mark.asyncio
async def test_deserialize_jsonld_validation_error_becomes_request_validation_error():
    request = request_with_body(b"{}", JSONLD_CONTENT_TYPE)

    with pytest.raises(RequestValidationError):
        await deserialize(RequiredFieldSchema)(request)


@pytest.mark.asyncio
async def test_deserialize_shaped_body_validation_error_becomes_request_validation_error():
    request = request_with_body(b'{"data": "{}"}', "application/vnd.sinopia+json")

    with pytest.raises(RequestValidationError):
        await deserialize(RequiredFieldSchema)(request)


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", [JSONLD_CONTENT_TYPE, "application/json"])
async def test_deserialize_names_the_bibframe_json_context(content_type):
    """A body echoing back our @context URL must not be left for rdflib to resolve."""
    jsonld = {"@context": CONTEXT_URL, "@id": "https://bcld.info/works/1"}
    body = (
        json.dumps(jsonld)
        if content_type == JSONLD_CONTENT_TYPE
        else json.dumps({"data": json.dumps(jsonld)})
    )
    request = request_with_body(body.encode(), content_type)

    parsed = await deserialize(DataOnlySchema)(request)

    assert json.loads(parsed.data)["@context"] == BIBFRAME_CONTEXT_URL


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", [JSONLD_CONTENT_TYPE, "application/json"])
async def test_deserialize_inline_context_raises_unprocessable_entity(content_type):
    """An inline context can reference a remote one, so it is refused, not parsed."""
    jsonld = {"@context": CONTEXT, "@id": "https://bcld.info/works/1"}
    body = (
        json.dumps(jsonld)
        if content_type == JSONLD_CONTENT_TYPE
        else json.dumps({"data": json.dumps(jsonld)})
    )
    request = request_with_body(body.encode(), content_type)

    with pytest.raises(HTTPException) as error:
        await deserialize(DataOnlySchema)(request)

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_deserialize_invalid_jsonld_data_raises_unprocessable_entity():
    request = request_with_body(b'{"data": "{"}', "application/vnd.sinopia+json")

    with pytest.raises(HTTPException) as error:
        await deserialize(DataOnlySchema)(request)

    assert error.value.status_code == 422
    assert "Invalid JSON-LD data" in error.value.detail


@pytest.mark.asyncio
async def test_deserialize_rdfxml_reads_it_into_jsonld_data():
    request = request_with_body(
        b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
            xmlns:bf="http://id.loc.gov/ontologies/bibframe/">
          <bf:Work rdf:about="https://example.com/work"/>
        </rdf:RDF>""",
        RDFXML_CONTENT_TYPE,
    )

    parsed = await deserialize(DataOnlySchema)(request)

    assert json.loads(parsed.data) == [
        {
            "@id": "https://example.com/work",
            "@type": ["http://id.loc.gov/ontologies/bibframe/Work"],
        }
    ]


@pytest.mark.asyncio
async def test_deserialize_invalid_rdfxml_raises_unprocessable_entity():
    request = request_with_body(b"<rdf:RDF", RDFXML_CONTENT_TYPE + "; charset=utf-8")

    with pytest.raises(HTTPException) as error:
        await deserialize(DataOnlySchema)(request)

    assert error.value.status_code == 422
    assert "Invalid RDF/XML body" in error.value.detail
