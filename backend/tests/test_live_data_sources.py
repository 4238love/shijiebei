from app.data_sources import (
    HttpJsonDataSourceAdapter,
    SourceCatalog,
    SourceCategory,
)
from pathlib import Path
from uuid import uuid4


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class FakeHttpClient:
    def __init__(self, content: bytes):
        self.content = content
        self.requested_urls = []

    def get(self, url, timeout):
        self.requested_urls.append((url, timeout))
        return FakeResponse(self.content)


def workspace_tmp() -> Path:
    path = Path(".test-output") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_http_json_adapter_fetches_live_source_through_injected_client():
    tmp_path = workspace_tmp()
    content = b"""
    {
      "match": {"home_team": "Brazil", "away_team": "Croatia", "home_advantage": 1.08},
      "team_form": {
        "Brazil": {"avg_goals_for": 2.2, "avg_goals_against": 0.7},
        "Croatia": {"avg_goals_for": 1.4, "avg_goals_against": 1.1}
      },
      "rankings": {
        "Brazil": {"strength": 1.12},
        "Croatia": {"strength": 0.96}
      }
    }
    """
    client = FakeHttpClient(content)
    adapter = HttpJsonDataSourceAdapter(
        source_name="live-schedule",
        url="https://data-source.example/match.json",
        snapshot_dir=tmp_path / "snapshots",
        http_client=client,
    )

    dataset = adapter.build_prediction_dataset()

    assert client.requested_urls == [("https://data-source.example/match.json", 10)]
    assert dataset.home_team == "Brazil"
    assert dataset.away_team == "Croatia"


def test_source_catalog_requires_all_first_wave_categories():
    catalog = SourceCatalog(
        {
            SourceCategory.SCHEDULE: ["schedule-primary"],
            SourceCategory.TEAM_FORM: ["form-primary"],
            SourceCategory.RANKING: ["ranking-primary"],
            SourceCategory.INJURY: ["injury-primary"],
            SourceCategory.ODDS: ["odds-primary"],
            SourceCategory.NEWS_SENTIMENT: ["news-primary"],
            SourceCategory.PLAYER: ["player-primary"],
        }
    )

    assert catalog.missing_first_wave_categories() == []


def test_source_catalog_reports_missing_categories():
    catalog = SourceCatalog({SourceCategory.SCHEDULE: ["schedule-primary"]})

    assert SourceCategory.INJURY in catalog.missing_first_wave_categories()
    assert SourceCategory.PLAYER in catalog.missing_first_wave_categories()
