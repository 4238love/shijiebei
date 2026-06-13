import math

from app.backtesting import ActualResult, BacktestCase, run_backtest
from app.cross_source_validation import ConflictStatus
from app.prediction_engine import MatchPrediction, ScorelineProbability


def prediction(
    *,
    home_win: float,
    draw: float,
    away_win: float,
    top_scorelines: tuple[ScorelineProbability, ...],
) -> MatchPrediction:
    return MatchPrediction(
        home_team="Brazil",
        away_team="Croatia",
        weight_version="baseline",
        simulation_count=10_000,
        expected_goals={"home": 1.8, "away": 0.8},
        probabilities={"home_win": home_win, "draw": draw, "away_win": away_win},
        top_scorelines=top_scorelines,
        confidence_level="A",
    )


def test_backtest_calculates_outcome_probability_metrics():
    run = run_backtest(
        [
            BacktestCase(
                prediction=prediction(
                    home_win=0.6,
                    draw=0.25,
                    away_win=0.15,
                    top_scorelines=(ScorelineProbability(1, 0, 0.12),),
                ),
                actual_result=ActualResult(home_goals=1, away_goals=0),
                conflict_status=ConflictStatus.CONFIRMED,
            ),
            BacktestCase(
                prediction=prediction(
                    home_win=0.2,
                    draw=0.3,
                    away_win=0.5,
                    top_scorelines=(ScorelineProbability(0, 1, 0.1),),
                ),
                actual_result=ActualResult(home_goals=0, away_goals=0),
                conflict_status=ConflictStatus.CONFLICTING,
            ),
        ]
    )

    assert run.match_count == 2
    assert run.outcome_hit_rate == 0.5
    assert math.isclose(run.brier_score, 0.5125)
    assert math.isclose(run.log_loss, 0.8573992140459634)


def test_backtest_calculates_scoreline_top_n_hit_rate():
    run = run_backtest(
        [
            BacktestCase(
                prediction=prediction(
                    home_win=0.6,
                    draw=0.25,
                    away_win=0.15,
                    top_scorelines=(
                        ScorelineProbability(2, 0, 0.1),
                        ScorelineProbability(1, 0, 0.09),
                    ),
                ),
                actual_result=ActualResult(home_goals=1, away_goals=0),
                conflict_status=ConflictStatus.CONFIRMED,
            )
        ],
        scoreline_top_n=2,
    )

    assert run.scoreline_top_n_hit_rate == 1.0


def test_backtest_segments_confirmed_and_conflicting_matches():
    run = run_backtest(
        [
            BacktestCase(
                prediction=prediction(
                    home_win=0.6,
                    draw=0.25,
                    away_win=0.15,
                    top_scorelines=(ScorelineProbability(1, 0, 0.12),),
                ),
                actual_result=ActualResult(home_goals=1, away_goals=0),
                conflict_status=ConflictStatus.CONFIRMED,
            ),
            BacktestCase(
                prediction=prediction(
                    home_win=0.6,
                    draw=0.25,
                    away_win=0.15,
                    top_scorelines=(ScorelineProbability(1, 0, 0.12),),
                ),
                actual_result=ActualResult(home_goals=0, away_goals=1),
                conflict_status=ConflictStatus.CONFLICTING,
            ),
        ]
    )

    assert run.segments["confirmed"].match_count == 1
    assert run.segments["confirmed"].outcome_hit_rate == 1.0
    assert run.segments["conflicting"].match_count == 1
    assert run.segments["conflicting"].outcome_hit_rate == 0.0
