from app.cross_source_validation import (
    ConflictStatus,
    CrossSourceValidator,
    NormalizedFact,
    confidence_penalty,
)


def test_matching_facts_are_confirmed():
    validator = CrossSourceValidator(source_priority={"injury": ["official", "news"]})

    result = validator.validate(
        fact_type="injury",
        entity_key="Brazil:Neymar",
        facts=[
            NormalizedFact("injury", "Brazil:Neymar", "available", "official"),
            NormalizedFact("injury", "Brazil:Neymar", "available", "news"),
        ],
    )

    assert result.status == ConflictStatus.CONFIRMED
    assert result.value == "available"
    assert result.sources == ["official", "news"]


def test_conflicting_facts_use_data_type_specific_source_priority():
    validator = CrossSourceValidator(source_priority={"injury": ["official", "news"]})

    result = validator.validate(
        fact_type="injury",
        entity_key="Brazil:Neymar",
        facts=[
            NormalizedFact("injury", "Brazil:Neymar", "doubtful", "news"),
            NormalizedFact("injury", "Brazil:Neymar", "available", "official"),
        ],
    )

    assert result.status == ConflictStatus.CONFLICTING
    assert result.value == "available"
    assert result.conflicting_values == {
        "available": ["official"],
        "doubtful": ["news"],
    }


def test_missing_facts_are_reported():
    validator = CrossSourceValidator(source_priority={})

    result = validator.validate(
        fact_type="odds",
        entity_key="Brazil-Croatia:home_win",
        facts=[],
    )

    assert result.status == ConflictStatus.MISSING
    assert result.value is None


def test_stale_facts_are_reported_without_becoming_confirmed():
    validator = CrossSourceValidator(source_priority={"odds": ["market-a"]})

    result = validator.validate(
        fact_type="odds",
        entity_key="Brazil-Croatia:home_win",
        facts=[
            NormalizedFact(
                "odds",
                "Brazil-Croatia:home_win",
                1.82,
                "market-a",
                is_stale=True,
            )
        ],
    )

    assert result.status == ConflictStatus.STALE
    assert result.value is None


def test_non_confirmed_facts_add_confidence_penalty():
    assert confidence_penalty(ConflictStatus.CONFIRMED) == 0
    assert confidence_penalty(ConflictStatus.CONFLICTING) > confidence_penalty(
        ConflictStatus.MISSING
    )
    assert confidence_penalty(ConflictStatus.STALE) > 0
