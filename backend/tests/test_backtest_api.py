from fastapi.testclient import TestClient

from app.main import create_app


def backtest_request() -> dict:
    return {
        "cases": [
            {
                "prediction": {
                    "home_team": "Brazil",
                    "away_team": "Croatia",
                    "weight_version": "baseline",
                    "simulation_count": 10000,
                    "expected_goals": {"home": 1.8, "away": 0.8},
                    "probabilities": {
                        "home_win": 0.6,
                        "draw": 0.25,
                        "away_win": 0.15,
                    },
                    "top_scorelines": [
                        {"home_goals": 1, "away_goals": 0, "probability": 0.12}
                    ],
                    "confidence_level": "A",
                },
                "actual_result": {"home_goals": 1, "away_goals": 0},
                "conflict_status": "confirmed",
            },
            {
                "prediction": {
                    "home_team": "Argentina",
                    "away_team": "France",
                    "weight_version": "baseline",
                    "simulation_count": 10000,
                    "expected_goals": {"home": 1.4, "away": 1.2},
                    "probabilities": {
                        "home_win": 0.2,
                        "draw": 0.3,
                        "away_win": 0.5,
                    },
                    "top_scorelines": [
                        {"home_goals": 0, "away_goals": 1, "probability": 0.1}
                    ],
                    "confidence_level": "B",
                },
                "actual_result": {"home_goals": 0, "away_goals": 0},
                "conflict_status": "conflicting",
            },
        ],
        "scoreline_top_n": 1,
    }


def test_create_and_retrieve_backtest_run():
    client = TestClient(create_app())

    created = client.post("/backtests", json=backtest_request())

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["id"]
    assert created_body["match_count"] == 2
    assert created_body["outcome_hit_rate"] == 0.5
    assert created_body["scoreline_top_n_hit_rate"] == 0.5
    assert created_body["segments"]["confirmed"]["match_count"] == 1

    retrieved = client.get(f"/backtests/{created_body['id']}")

    assert retrieved.status_code == 200
    assert retrieved.json() == created_body


def test_empty_backtest_cases_return_400():
    client = TestClient(create_app())

    response = client.post("/backtests", json={"cases": []})

    assert response.status_code == 400
    assert response.json()["detail"] == "cases must not be empty"


def test_unknown_backtest_run_returns_404():
    client = TestClient(create_app())

    response = client.get("/backtests/not-found")

    assert response.status_code == 404
    assert response.json()["detail"] == "Backtest run not found"
