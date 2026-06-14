from fastapi.testclient import TestClient

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
    assert body["provider_name"] == "gpt"
    assert body["model_name"].startswith("gpt-")
    assert "Brazil vs Croatia" in body["content"]
    assert body["input_summary"]["probabilities"]["home_win"] == 0.58
    assert body["input_summary"]["conflict_statuses"][0]["status"] == "conflicting"


def test_create_ai_report_for_deepseek():
    client = TestClient(create_app())

    response = client.post("/ai-reports", json=report_request("deepseek"))

    assert response.status_code == 201
    body = response.json()
    assert body["provider_name"] == "deepseek"
    assert body["model_name"] == "deepseek-chat"


def test_unknown_ai_report_provider_is_rejected():
    client = TestClient(create_app())

    response = client.post("/ai-reports", json=report_request("claude"))

    assert response.status_code == 400
    assert response.json()["detail"] == "Only deepseek and gpt providers are supported"
