import json
from collections.abc import Callable, Mapping

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from bluecore_api.app.utils.jsonld import inline_context

JSONLD_CONTENT_TYPE = "application/ld+json"
SINOPIA_CONTENT_TYPE = "application/vnd.sinopia+json"


async def _request_payload(request: Request) -> tuple[object, str]:
    """Read the JSON body and normalized request media type."""
    try:
        payload = await request.json()
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail=f"Invalid JSON body: {error}")

    content_type = request.headers.get("content-type", "").split(";")[0].strip()
    return payload, content_type


def _normalize_data(payload: object) -> object:
    """Inline the Bluecore @context in a Sinopia-shaped body's 'data' string."""
    if not (isinstance(payload, dict) and isinstance(payload.get("data"), str)):
        return payload
    try:
        data = json.loads(payload["data"])
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail=f"Invalid JSON-LD data: {error}")
    return {**payload, "data": json.dumps(inline_context(data))}


def _validate_schema(schema: type[BaseModel], payload: object) -> BaseModel:
    """Validate payload as a FastAPI request body."""
    try:
        return schema.model_validate(payload)
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error


def deserialize(schema: type[BaseModel]) -> Callable:
    """
    FastAPI dependency parsing a PUT/POST body by Content-Type into 'schema'.

    'application/ld+json' bodies are raw JSON-LD and are wrapped as the
    schema's 'data' string; anything else (the Sinopia 'application/vnd.sinopia+json'
    body, or 'application/json' for backwards compatibility) is validated against
    the schema directly. Either way the endpoint receives a normal schema instance
    whose 'data' is a JSON-LD string.
    """

    async def dependency(request: Request) -> BaseModel:
        payload, content_type = await _request_payload(request)

        # Raw JSON-LD (application/ld+json): the whole body is the graph, so wrap
        # it as the schema's 'data' string.
        if content_type == JSONLD_CONTENT_TYPE:
            payload = {"data": json.dumps(inline_context(payload))}
        else:
            payload = _normalize_data(payload)

        # Sinopia (application/vnd.sinopia+json, or application/json for backwards
        # compatibility): already shaped like the schema
        # ({"data": "<json-ld string>", ...}), so validate it directly
        return _validate_schema(schema, payload)

    return dependency


def request_body_openapi(
    schema: type[BaseModel], jsonld_example: Mapping[str, object]
) -> dict[str, object]:
    """
    Document both accepted request bodies for a create/update endpoint.

    These routes read the raw request to support two body media types, so the
    request body is described here instead of by an auto-parsed body parameter:
    the Sinopia schema (with an executable example) and a raw JSON-LD example.
    """
    # Listed first so Swagger UI defaults to the human-readable, multi-line
    # JSON-LD example. The Sinopia body's 'data' is a JSON-LD string, which
    # Swagger can only render as an escaped one-liner.
    return {
        "requestBody": {
            "required": True,
            "content": {
                JSONLD_CONTENT_TYPE: {
                    "schema": {"type": "object"},
                    "example": jsonld_example,
                },
                SINOPIA_CONTENT_TYPE: {
                    "schema": schema.model_json_schema(),
                    "example": {"data": json.dumps(jsonld_example)},
                },
            },
        }
    }
