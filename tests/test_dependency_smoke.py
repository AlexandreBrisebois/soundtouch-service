"""Exercise the production Flask/Flasgger stack without starting hardware services."""
from unittest.mock import patch

from app.main import create_app


def test_dependency_smoke():
    with patch("app.main.jobs.start_daemon"), patch("app.main.discovery.start_device_cache"):
        client = create_app().test_client()
    assert client.get("/").status_code == 200
    assert client.get("/apidocs/").status_code == 200
    response = client.get("/apispec_1.json")
    assert response.status_code == 200
    assert response.get_json()["swagger"] == "2.0"


if __name__ == "__main__":
    test_dependency_smoke()
