import json

import pytest
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from bluecore_api.app.utils.deserializer import JSONLD_CONTENT_TYPE, deserialize


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
