from fastapi.testclient import TestClient

from app.main import create_app


def prediction_request() -> dict:
    return {
        "dataset": {
            "home_team": "Brazil",
            "away_team": "Croatia",
            "home": {"attack_index": 1.35, "defense_weakness": 0.82},
            "away": {"attack_index": 0.96, "defense_weakness": 1.05},
            "home_advantage": 1.08,
            "conflict_count": 0,
        },
        "weight_version": {
            "name": "baseline",
            "factors": {},
        },
        "simulation_count": 2_000,
        "seed": 20260613,
    }


def test_create_and_retrieve_match_prediction():
    client = TestClient(create_app())

    created = client.post("/predictions", json=prediction_request())

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["id"]
    assert created_body["home_team"] == "Brazil"
    assert created_body["away_team"] == "Croatia"
    assert set(created_body["probabilities"]) == {"home_win", "draw", "away_win"}
    assert len(created_body["top_scorelines"]) == 5

    retrieved = client.get(f"/predictions/{created_body['id']}")

    assert retrieved.status_code == 200
    assert retrieved.json() == created_body


def test_retrieving_unknown_prediction_returns_404():
    client = TestClient(create_app())

    response = client.get("/predictions/not-found")

    assert response.status_code == 404
    assert response.json()["detail"] == "Match prediction not found"
