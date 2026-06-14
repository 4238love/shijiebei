from app.cross_source_validation import ConflictStatus, ValidatedFact
from app.prediction_dataset_builder import build_prediction_dataset_from_validated_facts


def fact(
    fact_type: str,
    entity_key: str,
    value,
    status: ConflictStatus = ConflictStatus.CONFIRMED,
) -> ValidatedFact:
    return ValidatedFact(
        fact_type=fact_type,
        entity_key=entity_key,
        status=status,
        value=value,
        sources=["source-a"],
        conflicting_values={},
    )


def test_build_prediction_dataset_uses_ratings_and_team_form():
    dataset = build_prediction_dataset_from_validated_facts(
        home_team="Brazil",
        away_team="Croatia",
        validated_facts=[
            fact("team_rating", "Brazil", 2082),
            fact("team_rating", "Croatia", 1900),
            fact("team_match_goals_for", "Brazil", 2),
            fact("team_match_goals_against", "Brazil", 1),
            fact("team_match_goals_for", "Croatia", 1),
            fact("team_match_goals_against", "Croatia", 2),
        ],
        home_advantage=1.08,
    )

    assert dataset.home_team == "Brazil"
    assert dataset.away_team == "Croatia"
    assert dataset.home.attack_index > dataset.away.attack_index
    assert dataset.away.defense_weakness > dataset.home.defense_weakness
    assert dataset.home_advantage == 1.08


def test_build_prediction_dataset_turns_fact_conflicts_into_confidence_penalty():
    dataset = build_prediction_dataset_from_validated_facts(
        home_team="Brazil",
        away_team="Croatia",
        validated_facts=[
            fact(
                "injury_availability",
                "Neymar",
                "doubtful",
                status=ConflictStatus.CONFLICTING,
            ),
            fact(
                "news_sentiment",
                "bbc-world-cup-football",
                "negative",
                status=ConflictStatus.STALE,
            ),
        ],
    )

    assert dataset.conflict_count == 3


def test_build_prediction_dataset_uses_decimal_odds_as_market_strength_signal():
    dataset = build_prediction_dataset_from_validated_facts(
        home_team="Brazil",
        away_team="Croatia",
        validated_facts=[
            fact("decimal_odds", "Brazil", 1.80),
            fact("decimal_odds", "Croatia", 4.20),
        ],
    )

    assert dataset.home.attack_index > dataset.away.attack_index
    assert dataset.home.defense_weakness < dataset.away.defense_weakness


def test_build_prediction_dataset_penalizes_team_unavailable_players():
    dataset = build_prediction_dataset_from_validated_facts(
        home_team="Brazil",
        away_team="Croatia",
        validated_facts=[
            fact("team_unavailable_player_count", "Brazil", 2),
            fact("team_unavailable_player_count", "Croatia", 0),
        ],
    )

    assert dataset.home.attack_index < dataset.away.attack_index
    assert dataset.home.defense_weakness > dataset.away.defense_weakness


def test_build_prediction_dataset_uses_listed_player_count_as_squad_depth_signal():
    dataset = build_prediction_dataset_from_validated_facts(
        home_team="Brazil",
        away_team="Croatia",
        validated_facts=[
            fact("team_listed_player_count", "Brazil", 26),
            fact("team_listed_player_count", "Croatia", 20),
        ],
    )

    assert dataset.home.attack_index > dataset.away.attack_index
    assert dataset.home.defense_weakness < dataset.away.defense_weakness


def test_build_prediction_dataset_uses_team_news_sentiment_signal():
    dataset = build_prediction_dataset_from_validated_facts(
        home_team="Brazil",
        away_team="Croatia",
        validated_facts=[
            fact("team_news_sentiment", "Brazil", "positive"),
            fact("team_news_sentiment", "Croatia", "negative"),
        ],
    )

    assert dataset.home.attack_index > dataset.away.attack_index
    assert dataset.home.defense_weakness < dataset.away.defense_weakness
