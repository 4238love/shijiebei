from fastapi.testclient import TestClient

from app.ai_report_repository import InMemoryAIReportRepository
from app.ai_report_api import _provider
from app.ai_reports import OpenAICompatibleAIReportProvider
from app.main import create_app


def report_request(provider_name: str = "gpt") -> dict:
    return {
        "provider_name": provider_name,
        "prediction": {
            "home_team": "Brazil",
            "away_team": "Croatia",
            "weight_version": "baseline",
            "simulation_count": 10000,
            "expected_goals": {"home": 1.85, "away": 0.95},
            "probabilities": {
                "home_win": 0.58,
                "draw": 0.24,
                "away_win": 0.18,
            },
            "top_scorelines": [
                {"home_goals": 1, "away_goals": 0, "probability": 0.12}
            ],
            "confidence_level": "A",
        },
        "validated_facts": [
            {
                "fact_type": "injury_availability",
                "entity_key": "Neymar",
                "status": "conflicting",
                "value": "doubtful",
                "sources": ["injury-primary", "injury-secondary"],
                "conflicting_values": {
                    "doubtful": ["injury-primary"],
                    "available": ["injury-secondary"],
                },
            }
        ],
    }


def test_create_ai_report_for_gpt_without_mutating_prediction():
    client = TestClient(create_app())

    response = client.post("/ai-reports", json=report_request("gpt"))

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["provider_name"] == "gpt"
    assert body["model_name"].startswith("gpt-")
    assert "AI 复核报告" in body["content"]
    assert "统计模型最强结果" in body["content"]
    assert body["input_summary"]["probabilities"]["home_win"] == 0.58
    assert body["input_summary"]["language"] == "zh-CN"
    assert body["input_summary"]["conflict_statuses"][0]["status"] == "conflicting"


def test_create_ai_report_for_deepseek():
    client = TestClient(create_app())

    response = client.post("/ai-reports", json=report_request("deepseek"))

    assert response.status_code == 201
    body = response.json()
    assert body["provider_name"] == "deepseek"
    assert body["model_name"] == "deepseek-chat"


def test_create_and_retrieve_ai_report():
    client = TestClient(create_app())
    created = client.post("/ai-reports", json=report_request("gpt"))

    retrieved = client.get(f"/ai-reports/{created.json()['id']}")

    assert retrieved.status_code == 200
    assert retrieved.json() == created.json()


def test_ai_report_repository_survives_app_recreation():
    repository = InMemoryAIReportRepository()
    first_client = TestClient(create_app(ai_report_repository=repository))
    created = first_client.post("/ai-reports", json=report_request("deepseek")).json()

    second_client = TestClient(create_app(ai_report_repository=repository))
    retrieved = second_client.get(f"/ai-reports/{created['id']}")

    assert retrieved.status_code == 200
    assert retrieved.json() == created


def test_unknown_ai_report_returns_404():
    client = TestClient(create_app())

    response = client.get("/ai-reports/not-found")

    assert response.status_code == 404
    assert response.json()["detail"] == "AI report not found"


def test_unknown_ai_report_provider_is_rejected():
    client = TestClient(create_app())

    response = client.post("/ai-reports", json=report_request("claude"))

    assert response.status_code == 400
    assert response.json()["detail"] == "Only deepseek and gpt providers are supported"


def test_ai_report_provider_factory_uses_live_http_provider_when_enabled(monkeypatch):
    monkeypatch.setenv("AI_REPORT_MODE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    provider = _provider("gpt")

    assert isinstance(provider, OpenAICompatibleAIReportProvider)
    assert provider.provider_name == "gpt"


def test_ai_report_provider_factory_defaults_to_template_provider(monkeypatch):
    monkeypatch.delenv("AI_REPORT_MODE", raising=False)

    provider = _provider("deepseek")

    assert provider.provider_name == "deepseek"
    assert not isinstance(provider, OpenAICompatibleAIReportProvider)
