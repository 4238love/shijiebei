from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class TeamModel:
    attack_index: float
    defense_weakness: float


@dataclass(frozen=True)
class PredictionDataset:
    home_team: str
    away_team: str
    home: TeamModel
    away: TeamModel
    home_advantage: float = 1.0
    conflict_count: int = 0


@dataclass(frozen=True)
class WeightVersion:
    name: str
    factors: dict[str, float]


@dataclass(frozen=True)
class ScorelineProbability:
    home_goals: int
    away_goals: int
    probability: float


@dataclass(frozen=True)
class MatchPrediction:
    home_team: str
    away_team: str
    weight_version: str
    simulation_count: int
    expected_goals: dict[str, float]
    probabilities: dict[str, float]
    top_scorelines: tuple[ScorelineProbability, ...]
    confidence_level: str


def run_match_prediction(
    dataset: PredictionDataset,
    weight_version: WeightVersion,
    *,
    simulation_count: int = 10_000,
    seed: int | None = None,
) -> MatchPrediction:
    if simulation_count <= 0:
        raise ValueError("simulation_count must be positive")

    rng = random.Random(seed)
    home_expected_goals, away_expected_goals = _expected_goals(dataset, weight_version)
    outcomes = Counter[str]()
    scorelines = Counter[tuple[int, int]]()

    for _ in range(simulation_count):
        home_goals = _sample_poisson(home_expected_goals, rng)
        away_goals = _sample_poisson(away_expected_goals, rng)
        scorelines[(home_goals, away_goals)] += 1

        if home_goals > away_goals:
            outcomes["home_win"] += 1
        elif home_goals == away_goals:
            outcomes["draw"] += 1
        else:
            outcomes["away_win"] += 1

    probabilities = _outcome_probabilities(outcomes, simulation_count)
    top_scorelines = _top_scorelines(scorelines, simulation_count)
    confidence_level = _confidence_level(
        max(probabilities.values()),
        conflict_count=dataset.conflict_count,
    )

    return MatchPrediction(
        home_team=dataset.home_team,
        away_team=dataset.away_team,
        weight_version=weight_version.name,
        simulation_count=simulation_count,
        expected_goals={
            "home": round(home_expected_goals, 4),
            "away": round(away_expected_goals, 4),
        },
        probabilities=probabilities,
        top_scorelines=top_scorelines,
        confidence_level=confidence_level,
    )


def _expected_goals(
    dataset: PredictionDataset,
    weight_version: WeightVersion,
) -> tuple[float, float]:
    base_goal_rate = weight_version.factors.get("base_goal_rate", 1.35)
    home_multiplier = weight_version.factors.get("home_goal_multiplier", 1.0)
    away_multiplier = weight_version.factors.get("away_goal_multiplier", 1.0)

    home_expected_goals = (
        base_goal_rate
        * dataset.home.attack_index
        * dataset.away.defense_weakness
        * dataset.home_advantage
        * home_multiplier
    )
    away_expected_goals = (
        base_goal_rate
        * dataset.away.attack_index
        * dataset.home.defense_weakness
        * away_multiplier
    )

    return max(0.05, home_expected_goals), max(0.05, away_expected_goals)


def _sample_poisson(lam: float, rng: random.Random) -> int:
    threshold = math.exp(-lam)
    product = 1.0
    count = 0

    while product > threshold:
        count += 1
        product *= rng.random()

    return count - 1


def _outcome_probabilities(
    outcomes: Counter[str],
    simulation_count: int,
) -> dict[str, float]:
    home_win = outcomes["home_win"] / simulation_count
    draw = outcomes["draw"] / simulation_count
    away_win = 1.0 - home_win - draw

    return {
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,
    }


def _top_scorelines(
    scorelines: Counter[tuple[int, int]],
    simulation_count: int,
) -> tuple[ScorelineProbability, ...]:
    ranked = sorted(
        scorelines.items(),
        key=lambda item: (-item[1], item[0][0], item[0][1]),
    )

    return tuple(
        ScorelineProbability(
            home_goals=home_goals,
            away_goals=away_goals,
            probability=count / simulation_count,
        )
        for (home_goals, away_goals), count in ranked[:5]
    )


def _confidence_level(max_probability: float, *, conflict_count: int) -> str:
    if max_probability >= 0.58:
        index = 0
    elif max_probability >= 0.48:
        index = 1
    elif max_probability >= 0.38:
        index = 2
    else:
        index = 3

    index = min(3, index + min(conflict_count, 3))
    return ("S", "A", "B", "C")[index]
