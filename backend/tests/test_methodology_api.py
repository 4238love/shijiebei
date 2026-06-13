from fastapi.testclient import TestClient

from app.main import create_app


def test_methodology_endpoint_explains_real_prediction_boundaries():
    response = TestClient(create_app()).get("/methodology")

    assert response.status_code == 200
    body = response.json()
    assert body["monte_carlo"]["default_simulations"] == 10_000
    assert "Prediction Engine owns probabilities" in body["prediction_engine"]["principle"]
    assert body["ai_analysis"]["can_change_probabilities"] is False
    assert "cross_source_validation" in body
    assert "backtest_run" in body
