from importlib.metadata import version


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": version("bluecore-api")}


def test_health_version_matches_pyproject(client):
    """The reported version is the one declared in pyproject.toml."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).parents[2] / "pyproject.toml"
    with pyproject.open("rb") as fo:
        declared_version = tomllib.load(fo)["project"]["version"]

    response = client.get("/health")
    assert response.json()["version"] == declared_version


def test_health_is_public(keycloak_client):
    """Health checks must not require a Keycloak token."""
    response = keycloak_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
