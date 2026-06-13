from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from enum import StrEnum
from pathlib import Path
import re

from app.prediction_engine import PredictionDataset, TeamModel


class SourceCategory(StrEnum):
    SCHEDULE = "schedule"
    TEAM_FORM = "team_form"
    RANKING = "ranking"
    INJURY = "injury"
    ODDS = "odds"
    NEWS_SENTIMENT = "news_sentiment"
    PLAYER = "player"


FIRST_WAVE_SOURCE_CATEGORIES = (
    SourceCategory.SCHEDULE,
    SourceCategory.TEAM_FORM,
    SourceCategory.RANKING,
    SourceCategory.INJURY,
    SourceCategory.ODDS,
    SourceCategory.NEWS_SENTIMENT,
    SourceCategory.PLAYER,
)


@dataclass(frozen=True)
class SourceSnapshot:
    source_name: str
    path: Path
    content_hash: str


@dataclass(frozen=True)
class ScheduleMatch:
    source_name: str
    event_id: str
    home_team: str
    away_team: str
    kickoff_at: str | None
    status: str
    home_score: int | None = None
    away_score: int | None = None


class SourceIngestionStatus(StrEnum):
    INGESTED = "ingested"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass(frozen=True)
class SourceIngestionResult:
    source_name: str
    category: SourceCategory | None
    status: SourceIngestionStatus
    item_count: int
    snapshot: SourceSnapshot | None = None
    matches: tuple[ScheduleMatch, ...] = ()
    message: str | None = None


class SourceCatalog:
    def __init__(self, sources_by_category: dict[SourceCategory, list[str]]):
        self.sources_by_category = sources_by_category

    def missing_first_wave_categories(self) -> list[SourceCategory]:
        return [
            category
            for category in FIRST_WAVE_SOURCE_CATEGORIES
            if not self.sources_by_category.get(category)
        ]


class FixtureDataSourceAdapter:
    def __init__(self, *, source_name: str, fixture_path: Path, snapshot_dir: Path):
        self.source_name = source_name
        self.fixture_path = Path(fixture_path)
        self.snapshot_dir = Path(snapshot_dir)

    def fetch_snapshot(self) -> SourceSnapshot:
        content = self.fixture_path.read_bytes()
        content_hash = sha256(content).hexdigest()
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = self.snapshot_dir / (
            f"{_safe_name(self.source_name)}-{content_hash[:12]}{self.fixture_path.suffix}"
        )
        snapshot_path.write_bytes(content)

        return SourceSnapshot(
            source_name=self.source_name,
            path=snapshot_path,
            content_hash=content_hash,
        )

    def build_prediction_dataset(self) -> PredictionDataset:
        snapshot = self.fetch_snapshot()
        source_data = json.loads(snapshot.path.read_text(encoding="utf-8"))
        return _dataset_from_source_data(source_data)


class HttpJsonDataSourceAdapter:
    def __init__(
        self,
        *,
        source_name: str,
        url: str,
        snapshot_dir: Path,
        http_client=None,
        timeout_seconds: int = 10,
    ):
        self.source_name = source_name
        self.url = url
        self.snapshot_dir = Path(snapshot_dir)
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def fetch_snapshot(self) -> SourceSnapshot:
        response = self._http_client().get(self.url, timeout=self.timeout_seconds)
        response.raise_for_status()
        content = response.content
        content_hash = sha256(content).hexdigest()
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = self.snapshot_dir / f"{_safe_name(self.source_name)}-{content_hash[:12]}.json"
        snapshot_path.write_bytes(content)

        return SourceSnapshot(
            source_name=self.source_name,
            path=snapshot_path,
            content_hash=content_hash,
        )

    def build_prediction_dataset(self) -> PredictionDataset:
        snapshot = self.fetch_snapshot()
        source_data = json.loads(snapshot.path.read_text(encoding="utf-8"))
        return _dataset_from_source_data(source_data)

    def _http_client(self):
        if self.http_client is not None:
            return self.http_client

        import httpx

        return httpx


class EspnScoreboardDataSourceAdapter:
    def __init__(
        self,
        *,
        source_name: str,
        url: str,
        snapshot_dir: Path,
        http_client=None,
        timeout_seconds: int = 10,
    ):
        self.source_name = source_name
        self.raw_adapter = HttpJsonDataSourceAdapter(
            source_name=source_name,
            url=url,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
            timeout_seconds=timeout_seconds,
        )

    def ingest_schedule(self) -> SourceIngestionResult:
        snapshot = self.raw_adapter.fetch_snapshot()
        payload = json.loads(snapshot.path.read_text(encoding="utf-8"))
        matches = tuple(
            _schedule_matches_from_espn_scoreboard(
                payload,
                source_name=self.source_name,
            )
        )

        return SourceIngestionResult(
            source_name=self.source_name,
            category=SourceCategory.SCHEDULE,
            status=SourceIngestionStatus.INGESTED,
            item_count=len(matches),
            snapshot=snapshot,
            matches=matches,
        )


class HttpWebpageDataSourceAdapter:
    def __init__(
        self,
        *,
        source_name: str,
        url: str,
        snapshot_dir: Path,
        http_client=None,
        timeout_seconds: int = 10,
    ):
        self.source_name = source_name
        self.url = url
        self.snapshot_dir = Path(snapshot_dir)
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def ingest_snapshot(self) -> SourceIngestionResult:
        snapshot = self.fetch_snapshot()
        return SourceIngestionResult(
            source_name=self.source_name,
            category=None,
            status=SourceIngestionStatus.INGESTED,
            item_count=1,
            snapshot=snapshot,
            message="Snapshot captured; parser pending for this source.",
        )

    def fetch_snapshot(self) -> SourceSnapshot:
        response = _http_get_webpage(
            self._http_client(),
            self.url,
            timeout_seconds=self.timeout_seconds,
        )
        response.raise_for_status()
        content = response.content
        content_hash = sha256(content).hexdigest()
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = self.snapshot_dir / f"{_safe_name(self.source_name)}-{content_hash[:12]}.html"
        snapshot_path.write_bytes(content)

        return SourceSnapshot(
            source_name=self.source_name,
            path=snapshot_path,
            content_hash=content_hash,
        )

    def _http_client(self):
        if self.http_client is not None:
            return self.http_client

        import httpx

        return httpx


def _dataset_from_source_data(source_data: dict) -> PredictionDataset:
    match = source_data["match"]
    home_team = match["home_team"]
    away_team = match["away_team"]

    return PredictionDataset(
        home_team=home_team,
        away_team=away_team,
        home=_team_model(source_data, home_team),
        away=_team_model(source_data, away_team),
        home_advantage=match.get("home_advantage", 1.0),
        conflict_count=source_data.get("conflict_count", 0),
    )


def _team_model(source_data: dict, team_name: str) -> TeamModel:
    form = source_data["team_form"][team_name]
    ranking = source_data.get("rankings", {}).get(team_name, {})
    strength = ranking.get("strength", 1.0)

    attack_index = max(0.1, (form["avg_goals_for"] / 1.5) * strength)
    defense_weakness = max(0.1, (form["avg_goals_against"] / 1.2) / strength)

    return TeamModel(
        attack_index=round(attack_index, 4),
        defense_weakness=round(defense_weakness, 4),
    )


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()


def _schedule_matches_from_espn_scoreboard(
    payload: dict,
    *,
    source_name: str,
) -> list[ScheduleMatch]:
    matches: list[ScheduleMatch] = []

    for event in payload.get("events", []):
        competitors = _event_competitors(event)
        home = _competitor_by_home_away(competitors, "home")
        away = _competitor_by_home_away(competitors, "away")
        if home is None or away is None:
            continue

        home_team = _competitor_team_name(home)
        away_team = _competitor_team_name(away)
        if not home_team or not away_team:
            continue

        matches.append(
            ScheduleMatch(
                source_name=source_name,
                event_id=str(event.get("id", "")),
                home_team=home_team,
                away_team=away_team,
                kickoff_at=event.get("date"),
                status=_event_status(event),
                home_score=_optional_int(home.get("score")),
                away_score=_optional_int(away.get("score")),
            )
        )

    return matches


def _event_competitors(event: dict) -> list[dict]:
    competitions = event.get("competitions", [])
    if not competitions:
        return []

    return list(competitions[0].get("competitors", []))


def _competitor_by_home_away(competitors: list[dict], home_away: str) -> dict | None:
    return next(
        (
            competitor
            for competitor in competitors
            if competitor.get("homeAway") == home_away
        ),
        None,
    )


def _competitor_team_name(competitor: dict) -> str | None:
    team = competitor.get("team", {})
    return (
        team.get("displayName")
        or team.get("shortDisplayName")
        or team.get("name")
        or team.get("abbreviation")
    )


def _event_status(event: dict) -> str:
    status_type = event.get("status", {}).get("type", {})
    return status_type.get("description") or status_type.get("name") or "unknown"


def _optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _http_get_webpage(http_client, url: str, *, timeout_seconds: int):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    }
    try:
        return http_client.get(url, timeout=timeout_seconds, headers=headers)
    except TypeError:
        return http_client.get(url, timeout=timeout_seconds)
