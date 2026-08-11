from fastapi.testclient import TestClient

from soulseek_charts.api.application import application

client = TestClient(application)


def test_health_reports_the_version():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_every_chart_route_is_versioned():
    """The chart contract is public: a breaking change must mean a new version."""
    schema = client.get("/api/v1/openapi.json").json()

    chart_paths = [path for path in schema["paths"] if "chart" in path or "artists" in path]
    assert chart_paths
    assert all(path.startswith("/api/v1/") for path in chart_paths)


def test_page_size_above_the_maximum_is_rejected():
    response = client.get("/api/v1/charts/artists", params={"page_size": 10_000})

    assert response.status_code == 422
