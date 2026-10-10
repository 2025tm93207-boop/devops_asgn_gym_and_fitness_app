import pytest

from aceest import create_app

SAMPLE_CLIENT = {
    "name": "Ravi",
    "age": 30,
    "height": 175,
    "weight": 80,
    "program": "Muscle Gain (MG) – PPL",
    "target_weight": 85,
    "target_adherence": 90,
    "membership_expiry": "2099-12-31",
}


@pytest.fixture
def app(tmp_path):
    """A fresh app backed by its own temporary SQLite database per test."""
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATABASE": str(tmp_path / "test.db"),
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """A test client already logged in as the default admin."""
    resp = client.post("/api/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    return client


@pytest.fixture
def sample_client(auth_client):
    """Logged-in test client with SAMPLE_CLIENT already created."""
    resp = auth_client.post("/api/clients", json=SAMPLE_CLIENT)
    assert resp.status_code == 201
    return auth_client
