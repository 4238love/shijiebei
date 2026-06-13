from fastapi.testclient import TestClient

from app.health import get_database_probe
from app.main import create_app


def test_health_reports_backend_and_database_ok():
    app = create_app()

    async def reachable_database():
        return True

    app.dependency_overrides[get_database_probe] = lambda: reachable_database

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "backend",
        "database": "ok",
    }


def test_health_degrades_without_crashing_when_database_is_unavailable():
    app = create_app()

    async def unreachable_database():
        return False

    app.dependency_overrides[get_database_probe] = lambda: unreachable_database

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "service": "backend",
        "database": "unavailable",
    }
