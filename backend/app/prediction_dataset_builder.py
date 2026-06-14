from __future__ import annotations

from statistics import mean

from app.cross_source_validation import (
    ConflictStatus,
    ValidatedFact,
    confidence_penalty,
)
from app.prediction_engine import PredictionDataset, TeamModel


def build_prediction_dataset_from_validated_facts(
    *,
    home_team: str,
    away_team: str,
    validated_facts: list[ValidatedFact],
    home_advantage: float = 1.0,
) -> PredictionDataset:
    home_market_factor, away_market_factor = _market_strength_factors(
        home_team,
        away_team,
        validated_facts,
    )
    return PredictionDataset(
        home_team=home_team,
        away_team=away_team,
        home=_team_model(
            home_team,
            validated_facts,
            market_strength_factor=home_market_factor,
        ),
        away=_team_model(
            away_team,
            validated_facts,
            market_strength_factor=away_market_factor,
        ),
        home_advantage=home_advantage,
        conflict_count=sum(
            confidence_penalty(fact.status) for fact in validated_facts
        ),
    )


def _team_model(
    team_name: str,
    facts: list[ValidatedFact],
    *,
    market_strength_factor: float = 1.0,
) -> TeamModel:
    goals_for = _numeric_values(facts, fact_type="team_match_goals_for", entity_key=team_name)
    goals_against = _numeric_values(
        facts,
        fact_type="team_match_goals_against",
        entity_key=team_name,
    )
    ratings = _numeric_values(facts, fact_type="team_rating", entity_key=team_name)
    rankings = _numeric_values(
        facts,
        fact_type="team_ranking_position",
        entity_key=team_name,
    )
    unavailable_player_counts = _numeric_values(
        facts,
        fact_type="team_unavailable_player_count",
        entity_key=team_name,
    )
    results = _string_values(facts, fact_type="team_match_result", entity_key=team_name)

    attack_index = 1.0
    defense_weakness = 1.0

    if goals_for:
        attack_index *= _clamp(mean(goals_for) / 1.5, 0.65, 1.6)
    if goals_against:
        defense_weakness *= _clamp(mean(goals_against) / 1.2, 0.65, 1.6)
    if ratings:
        rating_factor = _clamp(mean(ratings) / 2000, 0.8, 1.25)
        attack_index *= rating_factor
        defense_weakness *= _clamp(1 / rating_factor, 0.75, 1.25)
    elif rankings:
        ranking_factor = _clamp(1.16 - (mean(rankings) / 200), 0.75, 1.2)
        attack_index *= ranking_factor
        defense_weakness *= _clamp(1 / ranking_factor, 0.8, 1.3)
    if results:
        attack_index *= _result_attack_factor(results)
    if unavailable_player_counts:
        attack_penalty, defense_penalty = _availability_factors(
            mean(unavailable_player_counts)
        )
        attack_index *= attack_penalty
        defense_weakness *= defense_penalty
    if market_strength_factor != 1.0:
        attack_index *= market_strength_factor
        defense_weakness *= _clamp(1 / market_strength_factor, 0.85, 1.18)

    return TeamModel(
        attack_index=round(max(0.1, attack_index), 4),
        defense_weakness=round(max(0.1, defense_weakness), 4),
    )


def _market_strength_factors(
    home_team: str,
    away_team: str,
    facts: list[ValidatedFact],
) -> tuple[float, float]:
    home_odds = _numeric_values(facts, fact_type="decimal_odds", entity_key=home_team)
    away_odds = _numeric_values(facts, fact_type="decimal_odds", entity_key=away_team)
    if not home_odds or not away_odds:
        return (1.0, 1.0)

    home_implied = 1 / mean(home_odds)
    away_implied = 1 / mean(away_odds)
    total = home_implied + away_implied
    if total <= 0:
        return (1.0, 1.0)

    return (
        _market_share_factor(home_implied / total),
        _market_share_factor(away_implied / total),
    )


def _market_share_factor(two_way_share: float) -> float:
    return _clamp(1 + (two_way_share - 0.5) * 0.4, 0.88, 1.12)


def _availability_factors(unavailable_count: float) -> tuple[float, float]:
    return (
        _clamp(1 - unavailable_count * 0.04, 0.84, 1.0),
        _clamp(1 + unavailable_count * 0.03, 1.0, 1.12),
    )


def _numeric_values(
    facts: list[ValidatedFact],
    *,
    fact_type: str,
    entity_key: str,
) -> list[float]:
    values: list[float] = []
    for fact in _usable_facts(facts, fact_type=fact_type, entity_key=entity_key):
        try:
            values.append(float(fact.value))
        except (TypeError, ValueError):
            continue
    return values


def _string_values(
    facts: list[ValidatedFact],
    *,
    fact_type: str,
    entity_key: str,
) -> list[str]:
    return [
        str(fact.value)
        for fact in _usable_facts(facts, fact_type=fact_type, entity_key=entity_key)
        if fact.value is not None
    ]


def _usable_facts(
    facts: list[ValidatedFact],
    *,
    fact_type: str,
    entity_key: str,
) -> list[ValidatedFact]:
    return [
        fact
        for fact in facts
        if fact.fact_type == fact_type
        and fact.entity_key == entity_key
        and fact.status in {ConflictStatus.CONFIRMED, ConflictStatus.CONFLICTING}
    ]


def _result_attack_factor(results: list[str]) -> float:
    score = 0
    for result in results:
        if result == "win":
            score += 1
        elif result == "loss":
            score -= 1
    return _clamp(1 + (score / max(1, len(results))) * 0.08, 0.9, 1.1)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
