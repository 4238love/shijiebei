from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.cross_source_validation import NormalizedFact
from app.data_sources import ScheduleMatch, SourceIngestionResult


@dataclass(frozen=True)
class ScheduledFixture:
    source_name: str
    home_team: str
    away_team: str
    kickoff_at: str | None
    event_id: str = ""


def target_prediction_date(configured_date: str | None = None) -> date:
    if configured_date:
        return date.fromisoformat(configured_date)

    return datetime.now().date() + timedelta(days=1)


def fixtures_from_results(
    results: list[SourceIngestionResult],
) -> list[ScheduledFixture]:
    fixtures: list[ScheduledFixture] = []
    seen: set[tuple[str, str, str | None]] = set()

    for result in results:
        for match in result.matches:
            _append_fixture(
                fixtures,
                seen,
                _fixture_from_schedule_match(match),
            )
        for fact in result.facts:
            fixture = _fixture_from_fact(fact, source_name=result.source_name)
            if fixture is not None:
                _append_fixture(fixtures, seen, fixture)

    return fixtures


def matches_for_date(
    fixtures: list[ScheduledFixture],
    *,
    target_date: date,
) -> list[ScheduledFixture]:
    matches: list[ScheduledFixture] = []
    seen: set[tuple[str, str]] = set()

    for fixture in fixtures:
        if fixture_date(fixture.kickoff_at) != target_date:
            continue

        key = (fixture.home_team.casefold(), fixture.away_team.casefold())
        if key in seen:
            continue

        seen.add(key)
        matches.append(fixture)

    return matches


def fixture_date(kickoff_at: str | None) -> date | None:
    if not kickoff_at:
        return None

    normalized = kickoff_at.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(normalized)
        except ValueError:
            return None


def _fixture_from_schedule_match(match: ScheduleMatch) -> ScheduledFixture:
    return ScheduledFixture(
        source_name=match.source_name,
        event_id=match.event_id,
        home_team=match.home_team,
        away_team=match.away_team,
        kickoff_at=match.kickoff_at,
    )


def _fixture_from_fact(
    fact: NormalizedFact,
    *,
    source_name: str,
) -> ScheduledFixture | None:
    if fact.fact_type != "fixture_kickoff":
        return None

    teams = str(fact.entity_key).split(" vs ", maxsplit=1)
    if len(teams) != 2:
        return None

    home_team, away_team = [team.strip() for team in teams]
    if not home_team or not away_team:
        return None

    return ScheduledFixture(
        source_name=source_name,
        home_team=home_team,
        away_team=away_team,
        kickoff_at=str(fact.value) if fact.value is not None else None,
    )


def _append_fixture(
    fixtures: list[ScheduledFixture],
    seen: set[tuple[str, str, str | None]],
    fixture: ScheduledFixture,
) -> None:
    key = (
        fixture.home_team.casefold(),
        fixture.away_team.casefold(),
        fixture.kickoff_at,
    )
    if key in seen:
        return

    seen.add(key)
    fixtures.append(fixture)
