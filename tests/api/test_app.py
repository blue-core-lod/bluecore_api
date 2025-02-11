import pytest

from fastapi.testclient import TestClient

from bluecore.app.main import app

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Blue Core API"}