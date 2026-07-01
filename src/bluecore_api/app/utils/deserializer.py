import json
from typing import Any, Callable, Type

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

JSONLD_CONTENT_TYPE = "application/ld+json"
SINOPIA_CONTENT_TYPE = "application/vnd.sinopia+json"


def deserialize(schema: Type[BaseModel]) -> Callable:
    """
    FastAPI dependency parsing a PUT/POST body by Content-Type into 'schema'.

    'application/ld+json' bodies are raw JSON-LD and are wrapped as the
    schema's 'data' string; anything else (the Sinopia 'application/vnd.sinopia+json'
    body, or 'application/json' for backwards compatibility) is validated against
    the schema directly. Either way the endpoint receives a normal schema instance
    whose 'data' is a JSON-LD string.
    """

    async def dependency(request: Request) -> BaseModel:
        payload = await request.json()
        content_type = request.headers.get("content-type", "").split(";")[0].strip()

        # Raw JSON-LD (application/ld+json): the whole body is the graph, so wrap
        # it as the schema's 'data' string.
        if content_type == JSONLD_CONTENT_TYPE:
            return schema(data=json.dumps(payload))

        # Sinopia (application/vnd.sinopia+json, or application/json for backwards
        # compatibility): already shaped like the schema
        # ({"data": "<json-ld string>", ...}), so validate it directly
        try:
            return schema(**payload)
        except ValidationError as error:
            raise RequestValidationError(error.errors())

    return dependency


def request_body_openapi(
    schema: Type[BaseModel], jsonld_example: dict[str, Any]
) -> dict:
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
