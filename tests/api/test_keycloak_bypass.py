"""Unit tests for BypassKeycloakForGet — which requests skip Keycloak auth.

This middleware is the ASGI wrapper that decides, before Keycloak runs, whether
a request is public. It is *not* exercised by the `client`/`app` fixtures (those
use `base_app` directly and override the auth dependencies), so the bypass logic
is tested here against the wrapper in isolation.

The path cases are driven off BypassKeycloakForGet.EXACT_PATHS / PREFIX_PATHS so
every allow-listed endpoint (and any added later) is covered automatically.
"""

import pytest

from bluecore_api.middleware.keycloak_auth import BypassKeycloakForGet

EXACT_PATHS = sorted(BypassKeycloakForGet.EXACT_PATHS)
PREFIX_PATHS = sorted(BypassKeycloakForGet.PREFIX_PATHS)


class _Recorder:
    """Minimal ASGI app stub that records whether it was the one invoked."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send) -> None:
        self.called = True


async def _route(method: str, path: str) -> tuple[_Recorder, _Recorder]:
    """Send a request and see where the wrapper sends it.

    There are two possible destinations:
      - `inner`    = the app WITHOUT a login check (the request got let through)
      - `keycloak` = the login check (the request has to prove who it is)

    Hand the wrapper a fake request for the given method (GET, POST, ...) and
    path (e.g. "/works/"), then return both destinations so the test can check
    which one got used. Only one of them should ever be hit.
    """
    inner, keycloak = _Recorder(), _Recorder()
    wrapper = BypassKeycloakForGet(app=inner, keycloak_middleware=keycloak)

    # The wrapper hands these two callbacks straight to whichever destination it
    # picks, and our fake destinations ignore them, so they can be empty stubs.
    async def receive():  # never actually used by the stubs
        return {}

    async def send(message):  # never actually used by the stubs
        return None

    # This dict is the bare-minimum description of a web request that the wrapper
    # needs to make its decision: the HTTP method and the URL path.
    await wrapper({"type": "http", "method": method, "path": path}, receive, send)
    return inner, keycloak


# --- Set GET paths circumvent Keycloak Auth  ----------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("path", EXACT_PATHS)
async def test_get_exact_path_bypasses_keycloak(path):
    """Every exact allow-listed path is public on GET."""
    inner, keycloak = await _route("GET", path)
    assert inner.called and not keycloak.called


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", PREFIX_PATHS)
async def test_get_prefix_path_bypasses_keycloak(prefix):
    """Every prefix allow-listed path is public on GET, including sub-paths
    (e.g. /works/<id>), which is the whole point of matching by prefix."""
    for path in (prefix, f"{prefix}some-sub-path"):
        inner, keycloak = await _route("GET", path)
        assert inner.called and not keycloak.called, path


# --- Everything else still goes through Keycloak ------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "path",
    ["/works/123", "/mcp", "/hubs/", "/resources/x", "/profiles/", "/profiles/x"],
)
async def test_mutating_methods_still_require_auth(method, path):
    """The bypass is GET-only; mutating verbs on allow-listed paths are protected."""
    inner, keycloak = await _route(method, path)
    assert keycloak.called and not inner.called


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/some/private/route", "/admin", "/docs/extra", "/openapi.json/x"]
)
async def test_get_unlisted_path_requires_auth(path):
    """Control: a GET that isn't allow-listed is not bypassed. Confirms the
    bypass is path-driven (GET alone doesn't open a route) and that exact paths
    match exactly (e.g. /docs/extra is not /docs)."""
    inner, keycloak = await _route("GET", path)
    assert keycloak.called and not inner.called


# --- CORS preflight -----------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/works/", "/some/private/route"])
async def test_options_always_bypasses(path):
    """OPTIONS (CORS preflight) is always public, regardless of path."""
    inner, keycloak = await _route("OPTIONS", path)
    assert inner.called and not keycloak.called
