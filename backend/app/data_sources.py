from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import html
import json
from enum import StrEnum
from pathlib import Path
import re
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
    facts: list[NormalizedFact] = []
    for match in matches:
        if match.home_score is None or match.away_score is None:
            continue
        if "final" not in match.status.lower():
            continue

        facts.extend(
            [
                NormalizedFact(
                    fact_type="team_match_goals_for",
                    entity_key=match.home_team,
                    value=match.home_score,
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="team_match_goals_against",
                    entity_key=match.home_team,
                    value=match.away_score,
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="team_match_result",
                    entity_key=match.home_team,
                    value=_match_result(match.home_score, match.away_score),
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="team_match_goals_for",
                    entity_key=match.away_team,
                    value=match.away_score,
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="team_match_goals_against",
                    entity_key=match.away_team,
                    value=match.home_score,
                    source_name=source_name,
                ),
                NormalizedFact(
                    fact_type="team_match_result",
                    entity_key=match.away_team,
                    value=_match_result(match.away_score, match.home_score),
                    source_name=source_name,
                ),
            ]
        )

    return facts


def _match_result(goals_for: int, goals_against: int) -> str:
    if goals_for > goals_against:
        return "win"
    if goals_for == goals_against:
        return "draw"

    return "loss"


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
        "out",
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
        "out",
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
