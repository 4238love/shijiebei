from pathlib import Path


def test_compose_defines_backend_frontend_and_postgres_services():
    compose = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    text = compose.read_text(encoding="utf-8")

    assert "backend:" in text
    assert "frontend:" in text
    assert "postgres:" in text


def test_backend_waits_for_postgres_healthcheck():
    compose = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    text = compose.read_text(encoding="utf-8")

    assert "healthcheck:" in text
    assert "pg_isready" in text
    assert "condition: service_healthy" in text
