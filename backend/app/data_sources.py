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
