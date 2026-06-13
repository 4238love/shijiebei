from __future__ import annotations

from dataclasses import dataclass
import math

from app.cross_source_validation import ConflictStatus
from app.prediction_engine import MatchPrediction


@dataclass(frozen=True)
class ActualResult:
    home_goals: int
    away_goals: int

    @property
    def outcome(self) -> str:
        if self.home_goals > self.away_goals:
            return "home_win"
        if self.home_goals == self.away_goals:
            return "draw"
        return "away_win"


@dataclass(frozen=True)
class BacktestCase:
    prediction: MatchPrediction
    actual_result: ActualResult
    conflict_status: ConflictStatus


@dataclass(frozen=True)
class BacktestSegment:
    match_count: int
    outcome_hit_rate: float


@dataclass(frozen=True)
class BacktestRun:
    match_count: int
    outcome_hit_rate: float
    brier_score: float
    log_loss: float
    scoreline_top_n_hit_rate: float
    segments: dict[str, BacktestSegment]


def run_backtest(
    cases: list[BacktestCase],
    *,
    scoreline_top_n: int = 5,
) -> BacktestRun:
    if not cases:
        raise ValueError("cases must not be empty")

    outcome_hits = [_predicted_outcome(case.prediction) == case.actual_result.outcome for case in cases]
    scoreline_hits = [_scoreline_hit(case, scoreline_top_n) for case in cases]
    brier_scores = [_brier_score(case.prediction, case.actual_result.outcome) for case in cases]
    log_losses = [_log_loss(case.prediction, case.actual_result.outcome) for case in cases]

    return BacktestRun(
        match_count=len(cases),
        outcome_hit_rate=_rate(outcome_hits),
        brier_score=sum(brier_scores) / len(brier_scores),
        log_loss=sum(log_losses) / len(log_losses),
        scoreline_top_n_hit_rate=_rate(scoreline_hits),
        segments=_segments(cases),
    )


def _predicted_outcome(prediction: MatchPrediction) -> str:
    return max(prediction.probabilities.items(), key=lambda item: item[1])[0]


def _scoreline_hit(case: BacktestCase, scoreline_top_n: int) -> bool:
    expected = (case.actual_result.home_goals, case.actual_result.away_goals)
    top_scorelines = case.prediction.top_scorelines[:scoreline_top_n]
    return any(
        (scoreline.home_goals, scoreline.away_goals) == expected
        for scoreline in top_scorelines
    )


def _brier_score(prediction: MatchPrediction, actual_outcome: str) -> float:
    outcomes = ("home_win", "draw", "away_win")
    return sum(
        (prediction.probabilities[outcome] - (1.0 if outcome == actual_outcome else 0.0))
        ** 2
        for outcome in outcomes
    )


def _log_loss(prediction: MatchPrediction, actual_outcome: str) -> float:
    probability = max(1e-15, prediction.probabilities[actual_outcome])
    return -math.log(probability)


def _segments(cases: list[BacktestCase]) -> dict[str, BacktestSegment]:
    by_status: dict[str, list[BacktestCase]] = {}
    for case in cases:
        by_status.setdefault(case.conflict_status.value, []).append(case)

    return {
        status: BacktestSegment(
            match_count=len(status_cases),
            outcome_hit_rate=_rate(
                [
                    _predicted_outcome(case.prediction) == case.actual_result.outcome
                    for case in status_cases
                ]
            ),
        )
        for status, status_cases in by_status.items()
    }


def _rate(values: list[bool]) -> float:
    return sum(1 for value in values if value) / len(values)
