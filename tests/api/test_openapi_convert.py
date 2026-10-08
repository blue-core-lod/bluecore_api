"""Tests that the generated OpenAPI spec describes the convert routes truthfully.

The convert routes read the raw request themselves so that a raw body works as
well as a multipart upload (see app/routes/convert.py). FastAPI can only see the
multipart `file` field, so it used to document that alone: every raw media type
these routes accept, and every error they raise, existed only in the docstring.
The requestBody and responses are therefore hand-written, and these tests derive
their expectations from the module constants the handlers themselves branch on,
so the constants are provably the single source of truth.
"""

import pytest

from bluecore_api.app.routes import convert

CONVERT_PATHS = ("/marc2xml", "/marc2bibframe")


@pytest.fixture(scope="module")
def openapi_schema(app):
    """The freshly generated spec.

    Same cache handling as tests/api/test_openapi_security.py: FastAPI caches
    the schema on `app.openapi_schema` and the `app` fixture is session-scoped,
    so clear it on the way in and on the way out.
    """
    app.openapi_schema = None
    yield app.openapi()
    app.openapi_schema = None


def test_request_body_documents_every_accepted_media_type(openapi_schema):
    expected = {
        "/marc2xml": {"multipart/form-data", *convert.MARC2XML_RAW_TYPES},
        "/marc2bibframe": {"multipart/form-data", *convert.MARC2BIBFRAME_RAW_TYPES},
    }
    for path, media_types in expected.items():
        body = openapi_schema["paths"][path]["post"]["requestBody"]
        assert set(body["content"]) == media_types
        # A body-less POST is a 415, so the spec must not call it valid.
        assert body["required"] is True


def test_multipart_is_documented_first(openapi_schema):
    """Order is load-bearing, in two places.

    Swagger UI defaults to the first media type, and fastapi-mcp derives a
    tool's body arguments from the first one alone -- and a raw
    `{"type": "string"}` body has no properties, so leading with one would
    leave the MCP tool with no way to send a payload. openapi_extra is
    deep-merged, which appends, so multipart stays first.
    """
    for path in CONVERT_PATHS:
        content = openapi_schema["paths"][path]["post"]["requestBody"]["content"]
        assert next(iter(content)) == "multipart/form-data"


def test_response_documents_every_serialization_offered(openapi_schema):
    content = openapi_schema["paths"]["/marc2bibframe"]["post"]["responses"]["200"][
        "content"
    ]
    assert set(content) == set(convert.BIBFRAME_SERIALIZATIONS)


def test_error_responses_use_the_shape_actually_raised(openapi_schema):
    """FastAPI's auto-422 is HTTPValidationError, a list of per-field errors.

    These routes never raise that: every 4xx is an HTTPException with a string
    detail, so the declarations in convert.py replace it.
    """
    expected = {
        "/marc2xml": {"413", "415", "422"},
        "/marc2bibframe": {"406", "413", "415", "422"},
    }
    for path, codes in expected.items():
        responses = openapi_schema["paths"][path]["post"]["responses"]
        assert codes <= set(responses)
        for code in codes:
            schema = responses[code]["content"]["application/json"]["schema"]
            assert schema["properties"]["detail"]["type"] == "string"


def test_source_base_uri_is_documented_as_an_optional_query_param(openapi_schema):
    params = openapi_schema["paths"]["/marc2bibframe"]["post"]["parameters"]
    param = next(p for p in params if p["name"] == "source_base_uri")
    assert param["in"] == "query"
    assert param["required"] is False
    assert param["schema"]["default"] == convert.DEFAULT_SOURCE_BASE_URI


def test_marc2xml_takes_no_source_base_uri(openapi_schema):
    """It emits MARCXML, which has no URIs to mint."""
    operation = openapi_schema["paths"]["/marc2xml"]["post"]
    names = {p["name"] for p in operation.get("parameters", [])}
    assert "source_base_uri" not in names
