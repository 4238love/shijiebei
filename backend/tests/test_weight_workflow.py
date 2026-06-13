from app.prediction_engine import PredictionDataset, TeamModel, WeightVersion, run_match_prediction
from app.weights import WeightRecommendationRegistry, WeightRecommendationStatus


def sample_dataset() -> PredictionDataset:
    return PredictionDataset(
        home_team="Brazil",
        away_team="Croatia",
        home=TeamModel(attack_index=1.35, defense_weakness=0.82),
        away=TeamModel(attack_index=0.96, defense_weakness=1.05),
        home_advantage=1.08,
    )


def test_inactive_weight_recommendation_does_not_change_active_weights():
    baseline = WeightVersion(name="baseline", factors={"base_goal_rate": 1.35})
    registry = WeightRecommendationRegistry(active_weight_version=baseline)

    recommendation = registry.create_recommendation(
        provider_name="gpt",
        proposed_factors={"base_goal_rate": 1.6},
        rationale="Home favorites were underweighted in backtest runs.",
    )

    prediction = run_match_prediction(
        sample_dataset(),
        registry.active_weight_version,
        simulation_count=1_000,
        seed=11,
    )

    assert recommendation.status == WeightRecommendationStatus.PROPOSED
    assert registry.active_weight_version == baseline
    assert prediction.weight_version == "baseline"


def test_recommendation_requires_review_and_backtest_before_activation():
    registry = WeightRecommendationRegistry(
        active_weight_version=WeightVersion(name="baseline", factors={"base_goal_rate": 1.35})
    )
    recommendation = registry.create_recommendation(
        provider_name="deepseek",
        proposed_factors={"base_goal_rate": 1.42},
        rationale="Calibration drift found in low-scoring matches.",
    )

    activated = registry.approve_recommendation(
        recommendation_id=recommendation.id,
        reviewer="operator",
        backtest_reference="backtest-run-001",
        new_version_name="baseline-plus-low-score-calibration",
    )

    assert activated.name == "baseline-plus-low-score-calibration"
    assert registry.active_weight_version == activated
    assert registry.get_recommendation(recommendation.id).status == (
        WeightRecommendationStatus.APPROVED
    )


def test_recommendation_without_backtest_cannot_be_activated():
    registry = WeightRecommendationRegistry(
        active_weight_version=WeightVersion(name="baseline", factors={})
    )
    recommendation = registry.create_recommendation(
        provider_name="gpt",
        proposed_factors={"home_goal_multiplier": 1.03},
        rationale="Small home advantage adjustment.",
    )

    try:
        registry.approve_recommendation(
            recommendation_id=recommendation.id,
            reviewer="operator",
            backtest_reference="",
            new_version_name="invalid",
        )
    except ValueError as error:
        assert str(error) == "backtest_reference is required"
    else:
        raise AssertionError("expected approval without backtest reference to fail")
