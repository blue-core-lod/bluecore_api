"""Tests that the generated OpenAPI spec says which routes require auth.

Authentication here happens outside FastAPI's dependency graph: BypassKeycloakForGet
is an ASGI wrapper that decides what is public before routing ever happens, and
KeycloakMiddleware validates the token. The schema generator can see neither, so
every protected route used to be documented as if it were public (issue #324).

BluecoreCheckPermissions now depends on `keycloak_scheme`, an OAuth2 SecurityBase.
FastAPI collects security requirements from the whole dependency tree, so that one
dependency gives every route guarded by BCP a `security` entry. main.py then hangs
401/403 responses off whatever carries such an entry.

The drift guard at the bottom is the test that matters over time: it derives the
expected answer from BypassKeycloakForGet's own allow-lists, so a route added later
that is protected at runtime but undocumented in the spec fails here.
"""

import pytest

from bluecore_api.middleware.bluecore_check_permissions import keycloak_scheme
from bluecore_api.middleware.keycloak_auth import BypassKeycloakForGet

SCHEME_NAME = "Keycloak"

HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)


@pytest.fixture(scope="module")
def openapi_schema(app):
    """The freshly generated spec.

    FastAPI caches the schema on `app.openapi_schema` and the `app` fixture is
    session-scoped, so clear the cache on both sides: on the way in so we don't
    inherit a schema built under different conditions, and on the way out so we
    don't hand our mutated copy to anything that runs later.
    """
    app.openapi_schema = None
    yield app.openapi()
    app.openapi_schema = None


def _operations(schema):
    """Yield (path, method, operation) for every operation in the spec.

    A path item also holds non-operation keys such as `parameters` and `summary`,
    hence filtering on the known HTTP verbs rather than taking everything.
    """
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method.lower() in HTTP_METHODS:
                yield path, method.lower(), operation


def _requires_keycloak_at_runtime(path: str, method: str) -> bool:
    """Would BypassKeycloakForGet send this request to Keycloak?

    Mirrors the wrapper's own logic against its own allow-lists, so this stays
    correct when those lists change. Spec paths have no "/api" prefix -- root_path
    is expressed in the spec's `servers` block -- so only the bare form is matched.
    """
    if method != "get":
        return True
    bypassed = path in BypassKeycloakForGet.EXACT_PATHS or any(
        path.startswith(prefix) for prefix in BypassKeycloakForGet.PREFIX_PATHS
    )
    return not bypassed


def _secured(operation) -> bool:
    return any(
        SCHEME_NAME in requirement for requirement in operation.get("security", [])
    )


# --- The scheme itself --------------------------------------------------------
def test_security_scheme_is_declared(openapi_schema):
    """Without this block Swagger UI has no Authorize button and no padlocks."""
    schemes = openapi_schema["components"]["securitySchemes"]
    assert SCHEME_NAME in schemes, (
        "No Keycloak security scheme in the spec. FastAPI only emits one when a "
        "fastapi.security.SecurityBase instance is reachable from some route's "
        "dependency tree -- check that BluecoreCheckPermissions.__call__ still "
        "declares its `token` parameter."
    )
    assert schemes[SCHEME_NAME]["type"] == "oauth2"
    assert "authorizationCode" in schemes[SCHEME_NAME]["flows"]


def test_security_scheme_points_at_the_bluecore_realm(openapi_schema):
    """The Authorize button sends the browser to these URLs, so they must be the
    externally reachable Keycloak, not KEYCLOAK_INTERNAL_URL."""
    flow = openapi_schema["components"]["securitySchemes"][SCHEME_NAME]["flows"][
        "authorizationCode"
    ]
    suffix = "/realms/bluecore/protocol/openid-connect"
    assert flow["authorizationUrl"].endswith(f"{suffix}/auth")
    assert flow["tokenUrl"].endswith(f"{suffix}/token")
    assert set(flow["scopes"]) == {"openid", "profile", "email"}


def test_scheme_does_not_enforce_auth(openapi_schema):
    """auto_error must stay False.

    The scheme is in the dependency tree of every protected route. With
    auto_error=True FastAPI would reject any request lacking an Authorization
    header before the handler runs, breaking DEVELOPER_MODE and this whole suite,
    neither of which sends one. Enforcement belongs to the middleware and to
    BluecoreCheckPermissions; the scheme is documentation.
    """
    assert keycloak_scheme.auto_error is False


# --- Which operations carry a requirement -------------------------------------
def test_write_operations_require_keycloak(openapi_schema):
    """Every mutating operation is behind Keycloak at runtime, so every one of
    them must say so in the spec."""
    undocumented = [
        f"{method.upper()} {path}"
        for path, method, operation in _operations(openapi_schema)
        if method in {"post", "put", "patch", "delete"} and not _secured(operation)
    ]
    assert not undocumented, (
        f"Mutating operations with no security requirement: {sorted(undocumented)}. "
        "Add a BluecoreCheckPermissions dependency to the route."
    )


def test_public_reads_are_not_marked_as_requiring_auth(openapi_schema):
    """The read side of the API is deliberately open; a padlock on these would
    tell catalogers and downstream consumers to go get a token they don't need."""
    public = [
        "/",
        "/health",
        "/context.jsonld",
        "/works/{work_uuid}",
        "/instances/{instance_uuid}",
        "/hubs/{hub_uuid}",
        "/profiles/",
        "/resources/",
        "/search/",
        "/works/{work_uuid}/versions",
        "/change_documents/works/feed",
    ]
    for path in public:
        operation = openapi_schema["paths"][path]["get"]
        assert not _secured(operation), (
            f"GET {path} is public but documented as secured"
        )


# --- The error responses those requirements imply -----------------------------
def test_secured_operations_document_401_and_403(openapi_schema):
    """A padlock with no failure modes listed is half an answer: callers need to
    know a bad token is 401 and a wrong role is 403."""
    missing = [
        f"{method.upper()} {path}"
        for path, method, operation in _operations(openapi_schema)
        if _secured(operation)
        and not {"401", "403"} <= set(operation.get("responses", {}))
    ]
    assert not missing, (
        f"Secured operations missing a 401 or 403 response: {sorted(missing)}. "
        "openapi_with_auth_responses() in app/main.py attaches these to anything "
        "carrying a security requirement."
    )


def test_public_operations_do_not_document_401_or_403(openapi_schema):
    """Control for the test above: the injection keys off `security`, so it must
    not leak onto the public routes."""
    spurious = [
        f"{method.upper()} {path}"
        for path, method, operation in _operations(openapi_schema)
        if not _secured(operation)
        and {"401", "403"} & set(operation.get("responses", {}))
    ]
    assert not spurious, (
        f"Public operations documenting an auth failure: {sorted(spurious)}"
    )


def test_auth_responses_do_not_clobber_route_defined_responses(openapi_schema):
    """The injection uses setdefault. /marc2xml declares its own 200 with an XML
    content type (convert.py) and that must survive."""
    responses = openapi_schema["paths"]["/marc2xml"]["post"]["responses"]
    assert "application/xml" in responses["200"]["content"]
    assert {"401", "403"} <= set(responses)


# --- Drift guard --------------------------------------------------------------
def test_spec_matches_what_keycloak_actually_protects(openapi_schema):
    """The spec must agree with BypassKeycloakForGet about every operation.

    This is the test that catches the next #324. Both directions are failures: a
    route protected at runtime but silent in the spec misleads clients into
    thinking it is open, and a route marked secured but actually public sends
    them chasing a token for nothing.
    """
    mismatches = []
    for path, method, operation in _operations(openapi_schema):
        expected = _requires_keycloak_at_runtime(path, method)
        if _secured(operation) is not expected:
            state = "documented as secured" if not expected else "documented as public"
            reality = "public at runtime" if not expected else "requires a token"
            mismatches.append(f"{method.upper()} {path}: {state} but {reality}")

    assert not mismatches, "Spec and BypassKeycloakForGet disagree:\n  " + "\n  ".join(
        sorted(mismatches)
    )
