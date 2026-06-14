from fastapi.testclient import TestClient

from app.main import create_app
from app.weight_repository import InMemoryWeightRepository


def test_create_weight_recommendation_does_not_change_active_weight_version():
    client = TestClient(create_app())

    baseline = client.get("/weights/active").json()
    created = client.post(
        "/weights/recommendations",
        json={
            "provider_name": "gpt",
            "proposed_factors": {"base_goal_rate": 1.45},
            "rationale": "Backtest drift in low-scoring matches.",
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["id"]
    assert body["provider_name"] == "gpt"
    assert body["status"] == "proposed"
    assert client.get("/weights/active").json() == baseline

    retrieved = client.get(f"/weights/recommendations/{body['id']}")

    assert retrieved.status_code == 200
    assert retrieved.json() == body


def test_approve_weight_recommendation_requires_backtest_and_activates_version():
    client = TestClient(create_app())
    recommendation = client.post(
        "/weights/recommendations",
        json={
            "provider_name": "deepseek",
            "proposed_factors": {"home_goal_multiplier": 1.03},
            "rationale": "Home favorites were underweighted in reviewed runs.",
        },
    ).json()

    approved = client.post(
        f"/weights/recommendations/{recommendation['id']}/approve",
        json={
            "reviewer": "operator",
            "backtest_reference": "backtest-run-001",
            "new_version_name": "baseline-home-calibration",
        },
    )

    assert approved.status_code == 200
    body = approved.json()
    assert body["name"] == "baseline-home-calibration"
    assert body["factors"]["home_goal_multiplier"] == 1.03
    assert client.get("/weights/active").json() == body


def test_approve_weight_recommendation_without_backtest_returns_400():
    client = TestClient(create_app())
    recommendation = client.post(
        "/weights/recommendations",
        json={
            "provider_name": "gpt",
            "proposed_factors": {"base_goal_rate": 1.5},
            "rationale": "Needs review.",
        },
    ).json()

    response = client.post(
        f"/weights/recommendations/{recommendation['id']}/approve",
        json={
            "reviewer": "operator",
            "backtest_reference": "",
            "new_version_name": "invalid",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "backtest_reference is required"


def test_unknown_weight_recommendation_provider_is_rejected():
    client = TestClient(create_app())

    response = client.post(
        "/weights/recommendations",
        json={
            "provider_name": "claude",
            "proposed_factors": {"base_goal_rate": 1.5},
            "rationale": "Unsupported provider should not enter review flow.",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only deepseek and gpt providers are supported"


def test_unknown_weight_recommendation_returns_404():
    client = TestClient(create_app())

    response = client.get("/weights/recommendations/not-found")

    assert response.status_code == 404
    assert response.json()["detail"] == "Weight recommendation not found"


def test_weight_recommendation_repository_survives_app_recreation():
    repository = InMemoryWeightRepository()
    first_client = TestClient(create_app(weight_repository=repository))
    recommendation = first_client.post(
        "/weights/recommendations",
        json={
            "provider_name": "deepseek",
            "proposed_factors": {"base_goal_rate": 1.42},
            "rationale": "Reviewed backtest drift.",
        },
    ).json()

    first_client.post(
        f"/weights/recommendations/{recommendation['id']}/approve",
        json={
            "reviewer": "operator",
            "backtest_reference": "backtest-run-002",
            "new_version_name": "baseline-goal-rate-calibration",
        },
    )

    second_client = TestClient(create_app(weight_repository=repository))

    retrieved = second_client.get(f"/weights/recommendations/{recommendation['id']}")
    active = second_client.get("/weights/active")

    assert retrieved.status_code == 200
    assert retrieved.json()["status"] == "approved"
    assert active.json() == {
        "name": "baseline-goal-rate-calibration",
        "factors": {"base_goal_rate": 1.42},
    }
