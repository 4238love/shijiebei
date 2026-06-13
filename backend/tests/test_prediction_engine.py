from app.prediction_engine import (
    PredictionDataset,
    TeamModel,
    WeightVersion,
    run_match_prediction,
)


def sample_dataset(conflict_count: int = 0) -> PredictionDataset:
    return PredictionDataset(
        home_team="Brazil",
        away_team="Croatia",
        home=TeamModel(attack_index=1.35, defense_weakness=0.82),
        away=TeamModel(attack_index=0.96, defense_weakness=1.05),
        home_advantage=1.08,
        conflict_count=conflict_count,
    )


def test_prediction_probabilities_sum_to_one():
    prediction = run_match_prediction(
        sample_dataset(),
        WeightVersion(name="baseline", factors={}),
        simulation_count=2_000,
        seed=20260613,
    )

    total = sum(prediction.probabilities.values())

    assert total == 1.0
    assert set(prediction.probabilities) == {"home_win", "draw", "away_win"}


def test_prediction_is_repeatable_with_same_seed():
    first = run_match_prediction(
        sample_dataset(),
        WeightVersion(name="baseline", factors={}),
        simulation_count=2_000,
        seed=42,
    )
    second = run_match_prediction(
        sample_dataset(),
        WeightVersion(name="baseline", factors={}),
        simulation_count=2_000,
        seed=42,
    )

    assert first == second


def test_prediction_returns_ranked_scoreline_distribution():
    prediction = run_match_prediction(
        sample_dataset(),
        WeightVersion(name="baseline", factors={}),
        simulation_count=2_000,
        seed=7,
    )

    assert len(prediction.top_scorelines) == 5
    assert prediction.top_scorelines[0].probability >= prediction.top_scorelines[-1].probability
    assert all(scoreline.probability > 0 for scoreline in prediction.top_scorelines)


def test_conflicts_reduce_confidence_level():
    clean = run_match_prediction(
        sample_dataset(conflict_count=0),
        WeightVersion(name="baseline", factors={}),
        simulation_count=2_000,
        seed=9,
    )
    conflicting = run_match_prediction(
        sample_dataset(conflict_count=3),
        WeightVersion(name="baseline", factors={}),
        simulation_count=2_000,
        seed=9,
    )

    confidence_rank = {"S": 4, "A": 3, "B": 2, "C": 1}
    assert confidence_rank[conflicting.confidence_level] < confidence_rank[clean.confidence_level]
