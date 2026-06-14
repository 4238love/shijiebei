from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import html
import json
from enum import StrEnum
from pathlib import Path
import re
import time
from urllib.parse import urljoin

from app.cross_source_validation import NormalizedFact
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

NEWS_NEGATIVE_TERMS = (
    "injury",
    "injured",
    "doubtful",
    "crisis",
    "concern",
    "pressure",
    "suspended",
    "loss",
)
NEWS_POSITIVE_TERMS = (
    "boost",
    "return",
    "fit",
    "confident",
    "strong",
    "available",
    "win",
)
NEWS_TEAM_NAMES = (
    "Argentina",
    "Australia",
    "Belgium",
    "Brazil",
    "Cameroon",
    "Canada",
    "Chile",
    "Colombia",
    "Costa Rica",
    "Croatia",
    "Denmark",
    "Ecuador",
    "Egypt",
    "England",
    "France",
    "Germany",
    "Ghana",
    "Iran",
    "Italy",
    "Japan",
    "Mexico",
    "Morocco",
    "Netherlands",
    "Nigeria",
    "Norway",
    "Poland",
    "Portugal",
    "Qatar",
    "Saudi Arabia",
    "Senegal",
    "Serbia",
    "South Korea",
    "Spain",
    "Switzerland",
    "Tunisia",
    "United States",
    "Uruguay",
    "USA",
    "Wales",
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
    facts: tuple[NormalizedFact, ...] = ()
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
        category: SourceCategory | None = SourceCategory.SCHEDULE,
        snapshot_dir: Path,
        http_client=None,
        timeout_seconds: int = 10,
    ):
        self.source_name = source_name
        self.category = category
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
            category=self.category,
            status=SourceIngestionStatus.INGESTED,
            item_count=len(matches),
            snapshot=snapshot,
            matches=matches,
            facts=tuple(
                _facts_from_espn_matches(
                    matches,
                    category=self.category,
                    source_name=self.source_name,
                )
            ),
        )


class EspnTeamScheduleDiscoveryDataSourceAdapter:
    max_team_schedules = 48
    cache_ttl_seconds = 900

    def __init__(
        self,
        *,
        source_name: str,
        url: str,
        category: SourceCategory | None = SourceCategory.TEAM_FORM,
        snapshot_dir: Path,
        http_client=None,
        timeout_seconds: int = 10,
    ):
        self.source_name = source_name
        self.url = url
        self.category = category
        self.snapshot_dir = Path(snapshot_dir)
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def ingest_team_form(self) -> SourceIngestionResult:
        snapshot = self.fetch_snapshot()
        payload = json.loads(snapshot.path.read_text(encoding="utf-8"))
        matches: list[ScheduleMatch] = []
        for schedule in payload.get("team_schedules", []):
            matches.extend(
                _schedule_matches_from_espn_scoreboard(
                    schedule.get("payload", {}),
                    source_name=self.source_name,
                )
            )
        facts = tuple(
            _team_form_facts_from_matches(
                tuple(matches),
                source_name=self.source_name,
            )
        )

        return SourceIngestionResult(
            source_name=self.source_name,
            category=self.category,
            status=SourceIngestionStatus.INGESTED,
            item_count=len(payload.get("team_schedules", [])),
            snapshot=snapshot,
            matches=tuple(matches),
            facts=facts,
            message=_webpage_ingestion_message(facts),
        )

    def fetch_snapshot(self) -> SourceSnapshot:
        cached_snapshot = _fresh_cached_snapshot(
            source_name=self.source_name,
            snapshot_dir=self.snapshot_dir,
            suffix=".json",
            max_age_seconds=self.cache_ttl_seconds,
        )
        if cached_snapshot is not None:
            return cached_snapshot

        team_index_response = _http_get_webpage(
            self._http_client(),
            self.url,
            timeout_seconds=self.timeout_seconds,
        )
        team_index_response.raise_for_status()
        team_index_payload = json.loads(_decode_http_content(team_index_response.content))
        team_entries = _espn_team_entries_from_index(team_index_payload)

        team_schedules: list[dict] = []
        errors: list[dict[str, str]] = []
        for team in team_entries[: self.max_team_schedules]:
            schedule_url = _espn_team_schedule_url(self.url, team_id=team["id"])
            try:
                schedule_response = _http_get_webpage(
                    self._http_client(),
                    schedule_url,
                    timeout_seconds=self.timeout_seconds,
                )
                schedule_response.raise_for_status()
                team_schedules.append(
                    {
                        "team": team,
                        "url": schedule_url,
                        "payload": json.loads(_decode_http_content(schedule_response.content)),
                    }
                )
            except Exception as error:
                errors.append(
                    {
                        "team_id": team["id"],
                        "team_name": team["name"],
                        "url": schedule_url,
                        "error": str(error),
                    }
                )

        payload = {
            "source_url": self.url,
            "team_index": team_index_payload,
            "team_count": len(team_entries),
            "team_schedules": team_schedules,
            "errors": errors,
        }
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        content_hash = sha256(content).hexdigest()
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = (
            self.snapshot_dir / f"{_safe_name(self.source_name)}-{content_hash[:12]}.json"
        )
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


class EspnTeamRosterDiscoveryDataSourceAdapter:
    max_team_rosters = 48
    cache_ttl_seconds = 900

    def __init__(
        self,
        *,
        source_name: str,
        url: str,
        category: SourceCategory | None = SourceCategory.PLAYER,
        snapshot_dir: Path,
        http_client=None,
        timeout_seconds: int = 10,
    ):
        self.source_name = source_name
        self.url = url
        self.category = category
        self.snapshot_dir = Path(snapshot_dir)
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def ingest_players(self) -> SourceIngestionResult:
        snapshot = self.fetch_snapshot()
        payload = json.loads(snapshot.path.read_text(encoding="utf-8"))
        facts = tuple(
            _espn_roster_facts_from_payload(
                payload.get("team_rosters", []),
                source_name=self.source_name,
            )
        )

        return SourceIngestionResult(
            source_name=self.source_name,
            category=self.category,
            status=SourceIngestionStatus.INGESTED,
            item_count=len(payload.get("team_rosters", [])),
            snapshot=snapshot,
            facts=facts,
            message=_webpage_ingestion_message(facts),
        )

    def fetch_snapshot(self) -> SourceSnapshot:
        cached_snapshot = _fresh_cached_snapshot(
            source_name=self.source_name,
            snapshot_dir=self.snapshot_dir,
            suffix=".json",
            max_age_seconds=self.cache_ttl_seconds,
        )
        if cached_snapshot is not None:
            return cached_snapshot

        team_index_response = _http_get_webpage(
            self._http_client(),
            self.url,
            timeout_seconds=self.timeout_seconds,
        )
        team_index_response.raise_for_status()
        team_index_payload = json.loads(_decode_http_content(team_index_response.content))
        team_entries = _espn_team_entries_from_index(team_index_payload)

        team_rosters: list[dict] = []
        errors: list[dict[str, str]] = []
        for team in team_entries[: self.max_team_rosters]:
            roster_url = _espn_team_roster_url(self.url, team_id=team["id"])
            try:
                roster_response = _http_get_webpage(
                    self._http_client(),
                    roster_url,
                    timeout_seconds=self.timeout_seconds,
                )
                roster_response.raise_for_status()
                team_rosters.append(
                    {
                        "team": team,
                        "url": roster_url,
                        "payload": json.loads(_decode_http_content(roster_response.content)),
                    }
                )
            except Exception as error:
                errors.append(
                    {
                        "team_id": team["id"],
                        "team_name": team["name"],
                        "url": roster_url,
                        "error": str(error),
                    }
                )

        payload = {
            "source_url": self.url,
            "team_index": team_index_payload,
            "team_count": len(team_entries),
            "team_rosters": team_rosters,
            "errors": errors,
        }
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        content_hash = sha256(content).hexdigest()
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = (
            self.snapshot_dir / f"{_safe_name(self.source_name)}-{content_hash[:12]}.json"
        )
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


class HttpWebpageDataSourceAdapter:
    def __init__(
        self,
        *,
        source_name: str,
        url: str,
        category: SourceCategory | None = None,
        snapshot_dir: Path,
        http_client=None,
        timeout_seconds: int = 10,
    ):
        self.source_name = source_name
        self.url = url
        self.category = category
        self.snapshot_dir = Path(snapshot_dir)
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def ingest_snapshot(self) -> SourceIngestionResult:
        snapshot = self.fetch_snapshot()
        content = snapshot.path.read_text(encoding="utf-8", errors="ignore")
        facts = tuple(
            _facts_from_webpage(
                content,
                category=self.category,
                source_name=self.source_name,
            )
        )
        return SourceIngestionResult(
            source_name=self.source_name,
            category=self.category,
            status=SourceIngestionStatus.INGESTED,
            item_count=max(1, len(facts)),
            snapshot=snapshot,
            facts=facts,
            message=_webpage_ingestion_message(facts),
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


class SportsMoleInjuryDataSourceAdapter:
    max_articles = 12

    def __init__(
        self,
        *,
        source_name: str,
        url: str,
        category: SourceCategory | None = SourceCategory.INJURY,
        snapshot_dir: Path,
        http_client=None,
        timeout_seconds: int = 10,
    ):
        self.source_name = source_name
        self.url = url
        self.category = category
        self.snapshot_dir = Path(snapshot_dir)
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def ingest_injuries(self) -> SourceIngestionResult:
        snapshot = self.fetch_snapshot()
        payload = json.loads(snapshot.path.read_text(encoding="utf-8"))
        facts = tuple(
            _sportsmole_injury_facts_from_articles(
                payload.get("articles", []),
                source_name=self.source_name,
            )
        )

        return SourceIngestionResult(
            source_name=self.source_name,
            category=self.category,
            status=SourceIngestionStatus.INGESTED,
            item_count=len(payload.get("articles", [])),
            snapshot=snapshot,
            facts=facts,
            message=_webpage_ingestion_message(facts),
        )

    def fetch_snapshot(self) -> SourceSnapshot:
        listing_response = _http_get_webpage(
            self._http_client(),
            self.url,
            timeout_seconds=self.timeout_seconds,
        )
        listing_response.raise_for_status()
        listing_html = _decode_http_content(listing_response.content)
        article_urls = _sportsmole_injury_article_urls(listing_html, base_url=self.url)
        articles: list[dict[str, str]] = []
        for article_url in article_urls[: self.max_articles]:
            article_response = _http_get_webpage(
                self._http_client(),
                article_url,
                timeout_seconds=self.timeout_seconds,
            )
            article_response.raise_for_status()
            articles.append(
                {
                    "url": article_url,
                    "content": _decode_http_content(article_response.content),
                }
            )

        payload = {
            "source_url": self.url,
            "listing_html": listing_html,
            "article_urls": article_urls,
            "articles": articles,
        }
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        content_hash = sha256(content).hexdigest()
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = (
            self.snapshot_dir / f"{_safe_name(self.source_name)}-{content_hash[:12]}.json"
        )
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


class TransfermarktInjuryDataSourceAdapter:
    def __init__(
        self,
        *,
        source_name: str,
        url: str,
        category: SourceCategory | None = SourceCategory.INJURY,
        snapshot_dir: Path,
        http_client=None,
        timeout_seconds: int = 10,
    ):
        self.source_name = source_name
        self.url = url
        self.category = category
        self.snapshot_dir = Path(snapshot_dir)
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def ingest_injuries(self) -> SourceIngestionResult:
        snapshot = self.fetch_snapshot()
        content = snapshot.path.read_text(encoding="utf-8", errors="ignore")
        facts = tuple(
            _transfermarkt_injury_facts_from_html(
                content,
                source_name=self.source_name,
            )
        )
        player_fact_count = sum(
            1 for fact in facts if fact.fact_type == "injury_availability"
        )

        return SourceIngestionResult(
            source_name=self.source_name,
            category=self.category,
            status=SourceIngestionStatus.INGESTED,
            item_count=player_fact_count,
            snapshot=snapshot,
            facts=facts,
            message=_webpage_ingestion_message(facts),
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
        snapshot_path = (
            self.snapshot_dir / f"{_safe_name(self.source_name)}-{content_hash[:12]}.html"
        )
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


class WorldFootballEloDataSourceAdapter:
    def __init__(
        self,
        *,
        source_name: str,
        url: str,
        category: SourceCategory | None = SourceCategory.RANKING,
        snapshot_dir: Path,
        http_client=None,
        timeout_seconds: int = 10,
    ):
        self.source_name = source_name
        self.url = url
        self.category = category
        self.snapshot_dir = Path(snapshot_dir)
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def ingest_rankings(self) -> SourceIngestionResult:
        snapshot = self.fetch_snapshot()
        payload = json.loads(snapshot.path.read_text(encoding="utf-8"))
        team_names = _elo_team_names_from_tsv(payload["team_names_tsv"])
        facts = tuple(
            _elo_ranking_facts_from_world_tsv(
                payload["ratings_tsv"],
                team_names=team_names,
                source_name=self.source_name,
            )
        )

        return SourceIngestionResult(
            source_name=self.source_name,
            category=self.category,
            status=SourceIngestionStatus.INGESTED,
            item_count=len(facts),
            snapshot=snapshot,
            facts=facts,
            message=_webpage_ingestion_message(facts),
        )

    def fetch_snapshot(self) -> SourceSnapshot:
        ratings_url = urljoin(self.url, "World.tsv")
        team_names_url = urljoin(self.url, "en.teams.tsv")
        ratings_tsv = _http_get_webpage(
            self._http_client(),
            ratings_url,
            timeout_seconds=self.timeout_seconds,
        ).content.decode("utf-8", errors="ignore")
        team_names_tsv = _http_get_webpage(
            self._http_client(),
            team_names_url,
            timeout_seconds=self.timeout_seconds,
        ).content.decode("utf-8", errors="ignore")
        payload = {
            "source_url": self.url,
            "ratings_url": ratings_url,
            "team_names_url": team_names_url,
            "ratings_tsv": ratings_tsv,
            "team_names_tsv": team_names_tsv,
        }
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        content_hash = sha256(content).hexdigest()
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = (
            self.snapshot_dir / f"{_safe_name(self.source_name)}-{content_hash[:12]}.json"
        )
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


def _fresh_cached_snapshot(
    *,
    source_name: str,
    snapshot_dir: Path,
    suffix: str,
    max_age_seconds: int,
) -> SourceSnapshot | None:
    if max_age_seconds <= 0:
        return None
    snapshot_dir = Path(snapshot_dir)
    if not snapshot_dir.exists():
        return None

    candidates = [
        path
        for path in snapshot_dir.glob(f"{_safe_name(source_name)}-*{suffix}")
        if path.is_file()
    ]
    if not candidates:
        return None

    latest_path = max(candidates, key=lambda path: path.stat().st_mtime)
    if time.time() - latest_path.stat().st_mtime > max_age_seconds:
        return None

    content = latest_path.read_bytes()
    return SourceSnapshot(
        source_name=source_name,
        path=latest_path,
        content_hash=sha256(content).hexdigest(),
    )


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
                home_score=_competitor_score(home),
                away_score=_competitor_score(away),
            )
        )

    return matches


def _espn_team_entries_from_index(payload: dict) -> list[dict[str, str]]:
    teams: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for sport in payload.get("sports", []):
        for league in sport.get("leagues", []):
            for item in league.get("teams", []):
                team = item.get("team", {})
                team_id = str(team.get("id") or "").strip()
                team_name = (
                    team.get("displayName")
                    or team.get("shortDisplayName")
                    or team.get("name")
                    or team.get("abbreviation")
                    or ""
                )
                team_name = _clean_entity_name(str(team_name))
                if not team_id or not team_name or team_id in seen_ids:
                    continue
                seen_ids.add(team_id)
                teams.append({"id": team_id, "name": team_name})

    return teams


def _espn_team_schedule_url(teams_url: str, *, team_id: str) -> str:
    if re.search(r"/teams(?:\?.*)?$", teams_url):
        return re.sub(r"/teams(?:\?.*)?$", f"/teams/{team_id}/schedule", teams_url)
    return urljoin(teams_url.rstrip("/") + "/", f"{team_id}/schedule")


def _espn_team_roster_url(teams_url: str, *, team_id: str) -> str:
    if re.search(r"/teams(?:\?.*)?$", teams_url):
        return re.sub(r"/teams(?:\?.*)?$", f"/teams/{team_id}/roster", teams_url)
    return urljoin(teams_url.rstrip("/") + "/", f"{team_id}/roster")


def _espn_roster_facts_from_payload(
    team_rosters: list[dict],
    *,
    source_name: str,
) -> list[NormalizedFact]:
    facts: list[NormalizedFact] = []
    seen_players: set[str] = set()
    for roster in team_rosters:
        team = roster.get("team", {})
        team_name = _clean_entity_name(str(team.get("name") or ""))
        player_names = _espn_roster_player_names(roster.get("payload", {}))
        for player_name in player_names:
            if player_name in seen_players:
                continue
            seen_players.add(player_name)
            facts.append(
                NormalizedFact(
                    fact_type="player_presence",
                    entity_key=player_name,
                    value="listed",
                    source_name=source_name,
                )
            )
        if team_name:
            facts.append(
                NormalizedFact(
                    fact_type="team_listed_player_count",
                    entity_key=team_name,
                    value=len(player_names),
                    source_name=source_name,
                )
            )

    return facts


def _espn_roster_player_names(payload: dict) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for athlete in payload.get("athletes", []):
        player_name = (
            athlete.get("displayName")
            or athlete.get("fullName")
            or athlete.get("shortName")
            or athlete.get("name")
            or ""
        )
        player_name = _clean_entity_name(str(player_name))
        if not player_name or player_name in seen:
            continue
        seen.add(player_name)
        names.append(player_name)
    return names


def _facts_from_espn_matches(
    matches: tuple[ScheduleMatch, ...],
    *,
    category: SourceCategory | None,
    source_name: str,
) -> list[NormalizedFact]:
    if category == SourceCategory.TEAM_FORM:
        return _team_form_facts_from_matches(matches, source_name=source_name)

    return [
        NormalizedFact(
            fact_type="fixture_kickoff",
            entity_key=f"{match.home_team} vs {match.away_team}",
            value=match.kickoff_at,
            source_name=source_name,
        )
        for match in matches
        if match.kickoff_at
    ]


def _team_form_facts_from_matches(
    matches: tuple[ScheduleMatch, ...],
    *,
    source_name: str,
) -> list[NormalizedFact]:
    latest_by_team: dict[str, tuple[str, int, int]] = {}
    for match in matches:
        if match.home_score is None or match.away_score is None:
            continue
        if not _is_completed_match_status(match.status):
            continue

        _record_latest_team_match(
            latest_by_team,
            team_name=match.home_team,
            kickoff_at=match.kickoff_at,
            goals_for=match.home_score,
            goals_against=match.away_score,
        )
        _record_latest_team_match(
            latest_by_team,
            team_name=match.away_team,
            kickoff_at=match.kickoff_at,
            goals_for=match.away_score,
            goals_against=match.home_score,
        )

    facts: list[NormalizedFact] = []
    for team_name, (_, goals_for, goals_against) in latest_by_team.items():
        facts.extend(
            [
                NormalizedFact(
                    fact_type="team_match_goals_for",
                    entity_key=team_name,
                    value=goals_for,
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="team_match_goals_against",
                    entity_key=team_name,
                    value=goals_against,
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="team_match_result",
                    entity_key=team_name,
                    value=_match_result(goals_for, goals_against),
                    source_name=source_name,
                ),
            ]
        )
    return facts


def _record_latest_team_match(
    latest_by_team: dict[str, tuple[str, int, int]],
    *,
    team_name: str,
    kickoff_at: str | None,
    goals_for: int,
    goals_against: int,
) -> None:
    sort_key = kickoff_at or ""
    current = latest_by_team.get(team_name)
    if current is None or sort_key >= current[0]:
        latest_by_team[team_name] = (sort_key, goals_for, goals_against)


def _match_result(goals_for: int, goals_against: int) -> str:
    if goals_for > goals_against:
        return "win"
    if goals_for == goals_against:
        return "draw"

    return "loss"


def _is_completed_match_status(status: str) -> bool:
    normalized = status.strip().lower()
    return any(
        marker in normalized
        for marker in ("final", "full time", "ft", "completed")
    )


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


def _competitor_score(competitor: dict) -> int | None:
    score = competitor.get("score")
    if isinstance(score, dict):
        return _optional_int(score.get("displayValue") or score.get("value"))
    return _optional_int(score)


def _event_status(event: dict) -> str:
    status_type = event.get("status", {}).get("type", {})
    if not status_type:
        competitions = event.get("competitions", [])
        if competitions:
            status_type = competitions[0].get("status", {}).get("type", {})
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
        response = http_client.get(
            url,
            timeout=timeout_seconds,
            headers=headers,
            follow_redirects=True,
        )
        if _looks_like_aws_waf(response):
            return http_client.get(url, timeout=timeout_seconds, follow_redirects=True)
        return response
    except TypeError:
        return http_client.get(url, timeout=timeout_seconds)


def _decode_http_content(content) -> str:
    if isinstance(content, str):
        return content
    return content.decode("utf-8", errors="ignore")


def _looks_like_aws_waf(response) -> bool:
    content = getattr(response, "content", b"")
    if isinstance(content, str):
        content_bytes = content.encode("utf-8", errors="ignore")
    else:
        content_bytes = content
    return b"awsWaf" in content_bytes or b"gokuProps" in content_bytes


def _facts_from_webpage(
    content: str,
    *,
    category: SourceCategory | None,
    source_name: str,
) -> list[NormalizedFact]:
    text = _html_to_text(content)
    if category == SourceCategory.SCHEDULE:
        return _schema_org_sports_event_schedule_facts(
            content,
            source_name=source_name,
        )
    if category == SourceCategory.INJURY:
        return _injury_facts(text, source_name=source_name)
    if category == SourceCategory.ODDS:
        return _odds_facts(content, source_name=source_name)
    if category == SourceCategory.NEWS_SENTIMENT:
        return _news_sentiment_facts(text, source_name=source_name)
    if category == SourceCategory.PLAYER:
        return _player_facts(content, source_name=source_name)
    if category == SourceCategory.RANKING:
        return _ranking_facts(text, source_name=source_name)

    title = _html_title(content)
    if title:
        return [
            NormalizedFact(
                fact_type="webpage_title",
                entity_key=source_name,
                value=title,
                source_name=source_name,
            )
        ]

    return []


def _schema_org_sports_event_schedule_facts(
    content: str,
    *,
    source_name: str,
) -> list[NormalizedFact]:
    facts: list[NormalizedFact] = []
    seen_matches: set[str] = set()
    for item in _schema_org_json_ld_items(content):
        if not _schema_org_item_has_type(item, "SportsEvent"):
            continue
        if str(item.get("sport", "")).lower() not in {"", "football", "soccer"}:
            continue

        home_team, away_team = _match_teams_from_event_name(str(item.get("name", "")))
        kickoff_at = item.get("startDate")
        match_key = f"{home_team} vs {away_team}"
        if (
            not home_team
            or not away_team
            or not kickoff_at
            or match_key in seen_matches
        ):
            continue

        seen_matches.add(match_key)
        facts.append(
            NormalizedFact(
                fact_type="fixture_kickoff",
                entity_key=match_key,
                value=kickoff_at,
                source_name=source_name,
            )
        )

    return facts


def _schema_org_json_ld_items(content: str) -> list[dict]:
    items: list[dict] = []
    pattern = re.compile(
        r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(content):
        raw_json = html.unescape(match.group(1)).strip()
        if not raw_json:
            continue
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        items.extend(_flatten_schema_org_json_ld(payload))

    return items


def _flatten_schema_org_json_ld(payload) -> list[dict]:
    if isinstance(payload, dict):
        graph = payload.get("@graph")
        if isinstance(graph, list):
            return [
                item
                for item in graph
                if isinstance(item, dict)
            ]
        return [payload]
    if isinstance(payload, list):
        return [
            item
            for item in payload
            if isinstance(item, dict)
        ]
    return []


def _schema_org_item_has_type(item: dict, type_name: str) -> bool:
    raw_type = item.get("@type")
    if isinstance(raw_type, list):
        return type_name in {str(value) for value in raw_type}
    return str(raw_type) == type_name


def _match_teams_from_event_name(event_name: str) -> tuple[str | None, str | None]:
    match = re.match(
        r"\s*([A-Z][A-Za-z' .-]{1,50}?)\s+(?:v|vs\.?|[-–—])\s+([A-Z][A-Za-z' .-]{1,50}?)\s*$",
        event_name,
        flags=re.IGNORECASE,
    )
    if not match:
        return (None, None)

    return (
        _clean_entity_name(match.group(1)),
        _clean_entity_name(match.group(2)),
    )


def _html_to_text(content: str) -> str:
    without_title = re.sub(
        r"<title[^>]*>.*?</title>",
        " ",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    without_scripts = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        " ",
        without_title,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _html_title(content: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
    if not match:
        return None

    return re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()


def _injury_facts(text: str, *, source_name: str) -> list[NormalizedFact]:
    statuses = (
        "ruled out",
        "doubtful",
        "injured",
        "suspended",
        "unavailable",
        "available",
        "returning",
        "returns",
    )
    pattern = re.compile(
        rf"\b([A-Z][A-Za-z' -]{{1,48}}?)\s+(?:is\s+|was\s+)?({'|'.join(statuses)})\b",
        re.IGNORECASE,
    )
    facts: list[NormalizedFact] = []
    seen: set[tuple[str, str]] = set()
    for match in pattern.finditer(text):
        player_name = _clean_entity_name(match.group(1))
        status = match.group(2).lower()
        if status in {"returning", "returns"}:
            status = "available"
        key = (player_name, status)
        if not player_name or key in seen:
            continue
        seen.add(key)
        facts.append(
            NormalizedFact(
                fact_type="injury_availability",
                entity_key=player_name,
                value=status,
                source_name=source_name,
            )
        )

    team_facts = _team_unavailable_player_count_facts(
        text,
        statuses=statuses,
        source_name=source_name,
    )
    if facts or team_facts:
        return [*facts, *team_facts]

    injury_signal_count = sum(
        len(re.findall(term, text, flags=re.IGNORECASE))
        for term in (r"\binjury\b", r"\binjuries\b", r"\binjured\b", r"\bdoubtful\b")
    )
    if injury_signal_count:
        return [
            NormalizedFact(
                fact_type="injury_feed_signal",
                entity_key=source_name,
                value=injury_signal_count,
                source_name=source_name,
            )
        ]

    return []


def _sportsmole_injury_article_urls(content: str, *, base_url: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"href=[\"']([^\"']*world-cup-2026/team-news/[^\"']*injury-suspension-list[^\"']*\.html)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(content):
        article_url = urljoin(base_url, html.unescape(match.group(1)))
        if article_url in seen:
            continue
        seen.add(article_url)
        urls.append(article_url)

    return urls


def _sportsmole_injury_facts_from_articles(
    articles: list[dict],
    *,
    source_name: str,
) -> list[NormalizedFact]:
    player_facts: list[NormalizedFact] = []
    seen_players: set[tuple[str, str]] = set()
    team_unavailable_counts: dict[str, int] = {}

    for article in articles:
        content = str(article.get("content", ""))
        article_facts, article_counts = _sportsmole_injury_facts_from_article(
            content,
            source_name=source_name,
        )
        for fact in article_facts:
            key = (fact.entity_key, str(fact.value))
            if key in seen_players:
                continue
            seen_players.add(key)
            player_facts.append(fact)
        for team_name, count in article_counts.items():
            team_unavailable_counts[team_name] = max(
                count,
                team_unavailable_counts.get(team_name, 0),
            )

    team_facts = [
        NormalizedFact(
            fact_type="team_unavailable_player_count",
            entity_key=team_name,
            value=count,
            source_name=source_name,
        )
        for team_name, count in sorted(team_unavailable_counts.items())
    ]
    return [*player_facts, *team_facts]


def _sportsmole_injury_facts_from_article(
    content: str,
    *,
    source_name: str,
) -> tuple[list[NormalizedFact], dict[str, int]]:
    headers = [
        {
            "start": match.start(),
            "end": match.end(),
            "text": _html_to_text(match.group(1)),
        }
        for match in re.finditer(
            r"<h2\b[^>]*>(.*?)</h2>",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
    ]
    facts: list[NormalizedFact] = []
    team_counts: dict[str, int] = {}

    for index, header in enumerate(headers):
        team_name = _sportsmole_team_heading(header["text"])
        if not team_name:
            continue
        next_start = headers[index + 1]["start"] if index + 1 < len(headers) else len(content)
        section = content[header["end"] : next_start]
        status_entries = _sportsmole_status_entries(section)
        if not status_entries:
            continue

        unavailable_count = 0
        for status, value_html in status_entries:
            player_names = _sportsmole_status_player_names(value_html)
            if status in {"out", "doubtful", "suspended"}:
                unavailable_count += len(player_names)
            for player_name in player_names:
                facts.append(
                    NormalizedFact(
                        fact_type="injury_availability",
                        entity_key=player_name,
                        value=status,
                        source_name=source_name,
                    )
                )
        team_counts[team_name] = unavailable_count

    return facts, team_counts


def _sportsmole_team_heading(value: str) -> str | None:
    team_name = _clean_entity_name(value)
    if not team_name:
        return None
    lowered = team_name.lower()
    if " vs" in lowered or " v " in lowered or "sports mole" in lowered:
        return None
    return _title_case_team_name(team_name)


def _sportsmole_status_entries(section: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    pattern = re.compile(
        r"<p\b[^>]*>\s*<strong\b[^>]*>\s*(Out|Doubtful|Suspended)\s*:?\s*(?:&nbsp;)?\s*</strong>\s*(.*?)</p>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(section):
        status = match.group(1).lower()
        entries.append((status, match.group(2)))
    return entries


def _sportsmole_status_player_names(value_html: str) -> list[str]:
    value_text = _html_to_text(value_html)
    if not value_text or value_text.lower().startswith("none"):
        return []

    names = [
        _clean_entity_name(_html_to_text(match.group(1)))
        for match in re.finditer(
            r"<a\b[^>]*>(.*?)</a>",
            value_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
    ]
    return [name for name in names if name]


def _transfermarkt_injury_facts_from_html(
    content: str,
    *,
    source_name: str,
) -> list[NormalizedFact]:
    player_facts: list[NormalizedFact] = []
    team_unavailable_counts: dict[str, int] = {}
    seen_players: set[tuple[str, str]] = set()

    for match in re.finditer(
        r"<tr\b[^>]*>(.*?)</tr>",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        row_html = match.group(1)
        player_name = _transfermarkt_row_player_name(row_html)
        if not player_name:
            continue

        status = _transfermarkt_row_injury_status(row_html)
        key = (player_name, status)
        if key in seen_players:
            continue
        seen_players.add(key)
        player_facts.append(
            NormalizedFact(
                fact_type="injury_availability",
                entity_key=player_name,
                value=status,
                source_name=source_name,
            )
        )

        team_name = _transfermarkt_row_team_name(
            row_html,
            player_name=player_name,
        )
        if team_name and status in {"injured", "suspended", "doubtful", "out", "unavailable"}:
            team_unavailable_counts[team_name] = (
                team_unavailable_counts.get(team_name, 0) + 1
            )

    team_facts = [
        NormalizedFact(
            fact_type="team_unavailable_player_count",
            entity_key=team_name,
            value=count,
            source_name=source_name,
        )
        for team_name, count in sorted(team_unavailable_counts.items())
    ]
    return [*player_facts, *team_facts]


def _transfermarkt_row_player_name(row_html: str) -> str | None:
    for match in re.finditer(
        r"<a\b[^>]*href=[\"'][^\"']*/profil/spieler/[^\"']*[\"'][^>]*>(.*?)</a>",
        row_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        player_name = _clean_entity_name(_html_to_text(match.group(1)))
        if player_name:
            return player_name

    return None


def _transfermarkt_row_team_name(row_html: str, *, player_name: str) -> str | None:
    for match in re.finditer(
        r"\b(?:title|alt)=[\"']([^\"']+)[\"']",
        row_html,
        flags=re.IGNORECASE,
    ):
        candidate = _clean_entity_name(html.unescape(match.group(1)))
        if candidate.casefold() == player_name.casefold():
            continue
        if _looks_like_team_name(candidate):
            return _title_case_team_name(candidate)

    return None


def _transfermarkt_row_injury_status(row_html: str) -> str:
    row_text = _html_to_text(row_html).lower()
    if re.search(r"\b(suspended|suspension|ban|banned)\b", row_text):
        return "suspended"
    if re.search(r"\b(doubtful|questionable|fitness)\b", row_text):
        return "doubtful"
    if re.search(r"\b(ruled out|unavailable)\b", row_text):
        return "unavailable"
    if re.search(r"\bout\b", row_text):
        return "out"
    return "injured"


def _looks_like_team_name(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    if any(
        token in lowered
        for token in (
            "player",
            "profile",
            "injury",
            "suspended",
            "market value",
            "transfermarkt",
        )
    ):
        return False
    return bool(re.search(r"[A-Za-z]", value))


def _title_case_team_name(value: str) -> str:
    special_tokens = {"D.R.": "D.R.", "DR": "DR", "USA": "USA", "UAE": "UAE"}
    words = []
    for word in value.split():
        upper_word = word.upper()
        if upper_word in special_tokens:
            words.append(special_tokens[upper_word])
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _team_unavailable_player_count_facts(
    text: str,
    *,
    statuses: tuple[str, ...],
    source_name: str,
) -> list[NormalizedFact]:
    segment_pattern = re.compile(
        r"\b([A-Z][A-Za-z' .-]{1,32})\s*:\s*([^.;]+)",
        re.IGNORECASE,
    )
    status_pattern = re.compile(rf"\b({'|'.join(statuses)})\b", re.IGNORECASE)
    unavailable_statuses = {
        "ruled out",
        "doubtful",
        "injured",
        "suspended",
        "unavailable",
    }
    facts: list[NormalizedFact] = []
    seen_teams: set[str] = set()
    for segment in segment_pattern.finditer(text):
        team_name = _clean_entity_name(segment.group(1))
        if not team_name or team_name in seen_teams:
            continue

        statuses_in_segment = [
            match.group(1).lower() for match in status_pattern.finditer(segment.group(2))
        ]
        if not statuses_in_segment:
            continue

        seen_teams.add(team_name)
        unavailable_count = sum(
            1 for status in statuses_in_segment if status in unavailable_statuses
        )
        facts.append(
            NormalizedFact(
                fact_type="team_unavailable_player_count",
                entity_key=team_name,
                value=unavailable_count,
                source_name=source_name,
            )
        )

    return facts


def _odds_facts(text: str, *, source_name: str) -> list[NormalizedFact]:
    betexplorer_match_row_facts = _betexplorer_match_row_odds_facts(
        text,
        source_name=source_name,
    )
    if betexplorer_match_row_facts:
        return betexplorer_match_row_facts

    match_line_facts = _match_line_odds_facts(
        _html_to_text(text),
        source_name=source_name,
    )
    if match_line_facts:
        return match_line_facts

    pattern = re.compile(r"\b([A-Z][A-Za-z' -]{1,32})\s+([1-9]\d?\.\d{2})\b")
    facts: list[NormalizedFact] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        market = _clean_entity_name(match.group(1))
        if market in seen:
            continue
        seen.add(market)
        facts.append(
            NormalizedFact(
                fact_type="decimal_odds",
                entity_key=market,
                value=float(match.group(2)),
                source_name=source_name,
            )
        )

    if facts:
        return facts

    market_prices: list[NormalizedFact] = []
    seen_prices: set[float] = set()
    for index, match in enumerate(re.finditer(r"\b([1-9]\d?\.\d{2})\b", text), start=1):
        price = float(match.group(1))
        if price in seen_prices:
            continue
        seen_prices.add(price)
        market_prices.append(
            NormalizedFact(
                fact_type="market_decimal_odds",
                entity_key=f"market_price_{len(market_prices) + 1}",
                value=price,
                source_name=source_name,
            )
        )
        if len(market_prices) >= 20:
            break

    return market_prices


def _betexplorer_match_row_odds_facts(
    content: str,
    *,
    source_name: str,
) -> list[NormalizedFact]:
    facts: list[NormalizedFact] = []
    seen_matches: set[str] = set()
    for section in _betexplorer_relevant_odds_sections(content):
        row_starts = [
            match.start()
            for match in re.finditer(
                r"<li\b[^>]*table-main__tournamentLiContent[^>]*data-event-id=",
                section,
                flags=re.IGNORECASE,
            )
        ]
        for index, start in enumerate(row_starts):
            end = row_starts[index + 1] if index + 1 < len(row_starts) else len(section)
            row = section[start:end]
            home_team = _betexplorer_participant_name(row, "participantHome")
            away_team = _betexplorer_participant_name(row, "participantAway")
            odds = _betexplorer_row_decimal_odds(row)
            match_key = f"{home_team} vs {away_team}"
            if (
                not home_team
                or not away_team
                or len(odds) < 3
                or match_key in seen_matches
            ):
                continue

            seen_matches.add(match_key)
            facts.extend(
                [
                    NormalizedFact(
                        fact_type="decimal_odds",
                        entity_key=home_team,
                        value=odds[0],
                        source_name=source_name,
                    ),
                    NormalizedFact(
                        fact_type="match_draw_decimal_odds",
                        entity_key=match_key,
                        value=odds[1],
                        source_name=source_name,
                    ),
                    NormalizedFact(
                        fact_type="decimal_odds",
                        entity_key=away_team,
                        value=odds[2],
                        source_name=source_name,
                    ),
                ]
            )

    return facts


def _betexplorer_relevant_odds_sections(content: str) -> list[str]:
    markers = list(
        re.finditer(
            r'data-league-name=["\']World Championship 2026["\']',
            content,
            flags=re.IGNORECASE,
        )
    )
    if not markers:
        return [content]

    sections: list[str] = []
    for marker in markers:
        section_start = content.rfind("<ul", 0, marker.start())
        if section_start == -1:
            section_start = marker.start()
        next_section = re.search(
            r"<ul\b[^>]*leagues-list",
            content[marker.end() :],
            flags=re.IGNORECASE,
        )
        section_end = (
            marker.end() + next_section.start() if next_section else len(content)
        )
        sections.append(content[section_start:section_end])

    return sections


def _betexplorer_participant_name(row: str, class_fragment: str) -> str | None:
    match = re.search(
        rf"<[^>]*{class_fragment}[^>]*>.*?<p[^>]*>(.*?)</p>",
        row,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None

    team_name = _clean_entity_name(_html_to_text(match.group(1)))
    return team_name or None


def _betexplorer_row_decimal_odds(row: str) -> list[float]:
    odds: list[float] = []
    for match in re.finditer(r'\bdata-odd="([1-9]\d?(?:\.\d+)?)"', row):
        price = float(match.group(1))
        odds.append(price)
        if len(odds) >= 3:
            break

    return odds


def _match_line_odds_facts(text: str, *, source_name: str) -> list[NormalizedFact]:
    pattern = re.compile(
        r"\b([A-Z][A-Za-z' .-]{1,40}?)\s+(?:v|vs\.?|[-–—])\s+"
        r"([A-Z][A-Za-z' .-]{1,40}?)\s+"
        r"([1-9]\d?\.\d{2})\s+([1-9]\d?\.\d{2})\s+([1-9]\d?\.\d{2})\b",
        re.IGNORECASE,
    )
    facts: list[NormalizedFact] = []
    seen_matches: set[str] = set()
    for match in pattern.finditer(text):
        home_team = _clean_entity_name(match.group(1))
        away_team = _clean_entity_name(match.group(2))
        match_key = f"{home_team} vs {away_team}"
        if not home_team or not away_team or match_key in seen_matches:
            continue
        seen_matches.add(match_key)
        facts.extend(
            [
                NormalizedFact(
                    fact_type="decimal_odds",
                    entity_key=home_team,
                    value=float(match.group(3)),
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="match_draw_decimal_odds",
                    entity_key=match_key,
                    value=float(match.group(4)),
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="decimal_odds",
                    entity_key=away_team,
                    value=float(match.group(5)),
                    source_name=source_name,
                ),
            ]
        )

    return facts


def _news_sentiment_facts(text: str, *, source_name: str) -> list[NormalizedFact]:
    sentiment, _, _ = _sentiment_from_text(text)

    return [
        NormalizedFact(
            fact_type="news_sentiment",
            entity_key=source_name,
            value=sentiment,
            source_name=source_name,
        ),
        *_team_news_sentiment_facts(text, source_name=source_name),
    ]


def _team_news_sentiment_facts(
    text: str,
    *,
    source_name: str,
) -> list[NormalizedFact]:
    segment_pattern = re.compile(
        r"\b([A-Z][A-Za-z' .-]{1,32})\s*:\s*([^.;]+)",
    )
    facts: list[NormalizedFact] = []
    seen_teams: set[str] = set()
    for segment in segment_pattern.finditer(text):
        team_name = _clean_entity_name(segment.group(1))
        if not team_name or team_name in seen_teams:
            continue

        _append_team_news_sentiment_fact(
            facts,
            seen_teams=seen_teams,
            team_name=team_name,
            text=segment.group(2),
            source_name=source_name,
        )

    for clause in _news_sentiment_clauses(text):
        for team_name in _known_team_names_in_text(clause):
            _append_team_news_sentiment_fact(
                facts,
                seen_teams=seen_teams,
                team_name=team_name,
                text=clause,
                source_name=source_name,
            )

    return facts


def _append_team_news_sentiment_fact(
    facts: list[NormalizedFact],
    *,
    seen_teams: set[str],
    team_name: str,
    text: str,
    source_name: str,
) -> None:
    if team_name in seen_teams or not _is_known_news_team_name(team_name):
        return

    sentiment, positive_count, negative_count = _sentiment_from_text(text)
    if positive_count == 0 and negative_count == 0:
        return

    seen_teams.add(team_name)
    facts.append(
        NormalizedFact(
            fact_type="team_news_sentiment",
            entity_key=team_name,
            value=sentiment,
            source_name=source_name,
        )
    )


def _news_sentiment_clauses(text: str) -> list[str]:
    return [
        clause.strip()
        for clause in re.split(
            r"[.;!?]|\bbut\b|\bwhile\b|\bwhereas\b",
            text,
            flags=re.IGNORECASE,
        )
        if clause.strip()
    ]


def _known_team_names_in_text(text: str) -> list[str]:
    return [
        team_name
        for team_name in sorted(NEWS_TEAM_NAMES, key=len, reverse=True)
        if re.search(rf"\b{re.escape(team_name)}\b", text, flags=re.IGNORECASE)
    ]


def _is_known_news_team_name(team_name: str) -> bool:
    return team_name.lower() in {team.lower() for team in NEWS_TEAM_NAMES}


def _sentiment_from_text(text: str) -> tuple[str, int, int]:
    lower_text = text.lower()
    negative_count = sum(lower_text.count(term) for term in NEWS_NEGATIVE_TERMS)
    positive_count = sum(lower_text.count(term) for term in NEWS_POSITIVE_TERMS)
    sentiment = "neutral"
    if negative_count > positive_count:
        sentiment = "negative"
    elif positive_count > negative_count:
        sentiment = "positive"

    return (sentiment, positive_count, negative_count)


def _player_facts(text: str, *, source_name: str) -> list[NormalizedFact]:
    anchor_facts = _espn_player_anchor_facts(text, source_name=source_name)
    if anchor_facts:
        team_name = _team_name_from_squad_source_name(source_name)
        return [
            *anchor_facts,
            *_team_listed_player_count_facts(
                team_name=team_name,
                player_count=len(anchor_facts),
                source_name=source_name,
            ),
        ]

    text = _html_to_text(text)
    squad_match = re.search(
        r"\b(?:(?P<team>[A-Z][A-Za-z' .-]{1,32})\s+)?"
        r"(?:squad|players?)\s*:\s*(?P<players>[^.;]+)",
        text,
        re.IGNORECASE,
    )
    if not squad_match:
        return []

    facts: list[NormalizedFact] = []
    for raw_name in squad_match.group("players").split(","):
        player_name = _clean_entity_name(raw_name)
        if not player_name:
            continue
        facts.append(
            NormalizedFact(
                fact_type="player_presence",
                entity_key=player_name,
                value="listed",
                source_name=source_name,
            )
        )

    team_name = _clean_entity_name(squad_match.group("team") or "")
    return [
        *facts,
        *_team_listed_player_count_facts(
            team_name=team_name,
            player_count=len(facts),
            source_name=source_name,
        ),
    ]


def _team_listed_player_count_facts(
    *,
    team_name: str | None,
    player_count: int,
    source_name: str,
) -> list[NormalizedFact]:
    if not team_name:
        return []

    return [
        NormalizedFact(
            fact_type="team_listed_player_count",
            entity_key=team_name,
            value=player_count,
            source_name=source_name,
        )
    ]


def _team_name_from_squad_source_name(source_name: str) -> str | None:
    parts = _safe_name(source_name).split("-")
    if not parts or parts[-1] != "squad":
        return None
    team_parts = parts[:-1]
    if team_parts and team_parts[0] in {"espn", "fifa", "bbc"}:
        team_parts = team_parts[1:]
    if not team_parts:
        return None
    return " ".join(part.capitalize() for part in team_parts)


def _espn_player_anchor_facts(content: str, *, source_name: str) -> list[NormalizedFact]:
    pattern = re.compile(
        r"<a\b[^>]*data-resource-id=[\"']AthleteName[\"'][^>]*>(.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    facts: list[NormalizedFact] = []
    seen: set[str] = set()
    for match in pattern.finditer(content):
        player_name = _clean_entity_name(_html_to_text(match.group(1)))
        if not player_name or player_name in seen:
            continue
        seen.add(player_name)
        facts.append(
            NormalizedFact(
                fact_type="player_presence",
                entity_key=player_name,
                value="listed",
                source_name=source_name,
            )
        )

    return facts


def _ranking_facts(text: str, *, source_name: str) -> list[NormalizedFact]:
    pattern = re.compile(
        r"\b(\d{1,3})\s+([A-Z][A-Za-z' .-]{1,40}?)\s+(\d{3,4}(?:\.\d+)?)\b"
    )
    facts: list[NormalizedFact] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        team_name = _clean_entity_name(match.group(2))
        if not team_name or _looks_like_calendar_label(team_name) or team_name in seen:
            continue
        seen.add(team_name)
        facts.extend(
            [
                NormalizedFact(
                    fact_type="team_ranking_position",
                    entity_key=team_name,
                    value=int(match.group(1)),
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="team_rating",
                    entity_key=team_name,
                    value=float(match.group(3)),
                    source_name=source_name,
                ),
            ]
        )

    return facts


def _looks_like_calendar_label(value: str) -> bool:
    return value.lower() in {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }


def _elo_team_names_from_tsv(content: str) -> dict[str, str]:
    team_names: dict[str, str] = {}
    for line in content.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        code = fields[0].strip()
        name = _clean_entity_name(fields[1])
        if code and name:
            team_names[code] = name

    return team_names


def _elo_ranking_facts_from_world_tsv(
    content: str,
    *,
    team_names: dict[str, str],
    source_name: str,
) -> list[NormalizedFact]:
    facts: list[NormalizedFact] = []
    seen: set[str] = set()
    for line in content.splitlines():
        fields = line.split("\t")
        if len(fields) < 4:
            continue
        rank = _optional_int(fields[0])
        code = fields[2].strip()
        rating = _optional_float(fields[3])
        team_name = team_names.get(code, code)
        if rank is None or rating is None or not team_name or team_name in seen:
            continue
        seen.add(team_name)
        facts.extend(
            [
                NormalizedFact(
                    fact_type="team_ranking_position",
                    entity_key=team_name,
                    value=rank,
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="team_rating",
                    entity_key=team_name,
                    value=rating,
                    source_name=source_name,
                ),
            ]
        )

    return facts


def _clean_entity_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" -:,.")).strip()


def _optional_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _webpage_ingestion_message(facts: tuple[NormalizedFact, ...]) -> str:
    if facts:
        return f"Snapshot captured; extracted {len(facts)} normalized facts."

    return "Snapshot captured; parser pending for this source."
