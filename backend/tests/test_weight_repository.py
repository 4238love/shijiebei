from app.prediction_engine import WeightVersion
from app.weight_repository import InMemoryWeightRepository
from app.weights import WeightRecommendation, WeightRecommendationStatus


def test_in_memory_weight_repository_saves_and_retrieves_recommendation():
    repository = InMemoryWeightRepository()
    recommendation = WeightRecommendation(
        id="recommendation-1",
        provider_name="gpt",
        proposed_factors={"base_goal_rate": 1.45},
        rationale="Reviewed backtest drift.",
        status=WeightRecommendationStatus.PROPOSED,
    )

    repository.save_recommendation(recommendation)

    assert repository.get_recommendation("recommendation-1") == recommendation


def test_in_memory_weight_repository_returns_none_for_missing_recommendation():
    repository = InMemoryWeightRepository()

    assert repository.get_recommendation("missing") is None


def test_in_memory_weight_repository_saves_active_weight_version():
    repository = InMemoryWeightRepository()
    active = WeightVersion(
        name="baseline-home-calibration",
        factors={"base_goal_rate": 1.35, "home_goal_multiplier": 1.03},
    )

    repository.save_active_weight_version(active)

    assert repository.get_active_weight_version() == active
