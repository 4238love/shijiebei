import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.data_sources import EspnScoreboardDataSourceAdapter, HttpWebpageDataSourceAdapter
from app.main import create_app


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


class BrokenHttpClient:
    def get(self, url, timeout):
        raise RuntimeError("network blocked")


def workspace_tmp() -> Path:
    path = Path(".test-output") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def espn_scoreboard_payload() -> bytes:
    return json.dumps(
        {
            "events": [
                {
                    "id": "401752988",
                    "date": "2026-06-11T19:00Z",
                    "name": "Mexico vs Canada",
                    "status": {"type": {"description": "Scheduled"}},
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {"displayName": "Mexico"},
                                    "score": "0",
                                },
                                {
                                    "homeAway": "away",
                                    "team": {"displayName": "Canada"},
                                    "score": "0",
                                },
                            ]
                        }
                    ],
                }
            ]
        }
    ).encode()


def write_sources_config(path: Path):
    path.write_text(
        json.dumps(
            {
                "schedule": [
                    {
                        "name": "espn-world-cup-scoreboard",
                        "url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
                        "priority": 1,
                        "adapter": "espn_scoreboard",
                    }
                ],
                "team_form": [
                    {
                        "name": "manual-form",
                        "url": "https://data-source.example/form.json",
                        "priority": 1,
                    }
                ],
                "ranking": [
                    {
                        "name": "manual-ranking",
                        "url": "https://data-source.example/rankings.json",
                        "priority": 1,
                    }
                ],
                "injury": [
                    {
                        "name": "manual-injury",
                        "url": "https://data-source.example/injuries.json",
                        "priority": 1,
                    }
                ],
                "odds": [
                    {
                        "name": "manual-odds",
                        "url": "https://data-source.example/odds.json",
                        "priority": 1,
                    }
                ],
                "news_sentiment": [
                    {
                        "name": "manual-news",
                        "url": "https://data-source.example/news.json",
                        "priority": 1,
                    }
                ],
                "player": [
                    {
                        "name": "manual-player",
                        "url": "https://data-source.example/players.json",
                        "priority": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_espn_scoreboard_adapter_saves_snapshot_and_parses_schedule_matches():
    tmp_path = workspace_tmp()
    http_client = FakeHttpClient(espn_scoreboard_payload())
    adapter = EspnScoreboardDataSourceAdapter(
        source_name="espn-world-cup-scoreboard",
        url="https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    )

    result = adapter.ingest_schedule()

    assert http_client.requested_urls == [
        (
            "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
            10,
        )
    ]
    assert result.status == "ingested"
    assert result.item_count == 1
    assert result.snapshot is not None
    assert result.snapshot.path.exists()
    assert result.matches[0].event_id == "401752988"
    assert result.matches[0].home_team == "Mexico"
    assert result.matches[0].away_team == "Canada"
    assert result.matches[0].kickoff_at == "2026-06-11T19:00Z"


def test_webpage_adapter_saves_html_snapshot_for_parser_pending_sources():
    tmp_path = workspace_tmp()
    http_client = FakeHttpClient(
        b"<html><title>World Cup injuries</title><body>Player doubtful</body></html>"
    )
    adapter = HttpWebpageDataSourceAdapter(
        source_name="transfermarkt-world-cup-2026-injuries",
        url="https://www.transfermarkt.com/world-cup-2026/verletztespieler/pokalwettbewerb/WM26",
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    )

    result = adapter.ingest_snapshot()

    assert result.status == "ingested"
    assert result.item_count == 1
    assert result.snapshot is not None
    assert result.snapshot.path.suffix == ".html"
    assert "parser pending" in result.message


def test_sources_api_lists_configured_source_catalog():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    write_sources_config(config_path)
    client = TestClient(create_app(source_config_path=config_path))

    response = client.get("/sources")

    assert response.status_code == 200
    body = response.json()
    assert body["missing_first_wave_categories"] == []
    assert body["sources"][0]["name"] == "espn-world-cup-scoreboard"
    assert body["sources"][0]["adapter"] == "espn_scoreboard"


def test_sources_api_ingests_espn_scoreboard_source():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    write_sources_config(config_path)
    http_client = FakeHttpClient(espn_scoreboard_payload())
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=http_client,
        )
    )

    response = client.post(
        "/sources/ingest",
        json={"category": "schedule", "source_name": "espn-world-cup-scoreboard"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["source_name"] == "espn-world-cup-scoreboard"
    assert body["results"][0]["status"] == "ingested"
    assert body["results"][0]["item_count"] == 1
    assert body["results"][0]["matches"][0]["home_team"] == "Mexico"
    assert body["results"][0]["matches"][0]["away_team"] == "Canada"


def test_sources_api_ingests_configured_webpage_snapshot_without_parsing_it():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    write_sources_config(config_path)
    http_client = FakeHttpClient(b"<html><body>Injury report</body></html>")
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=http_client,
        )
    )

    response = client.post(
        "/sources/ingest",
        json={"category": "injury", "source_name": "manual-injury"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["source_name"] == "manual-injury"
    assert body["results"][0]["status"] == "ingested"
    assert body["results"][0]["item_count"] == 1
    assert body["results"][0]["matches"] == []


def test_sources_api_reports_failed_source_without_failing_entire_ingestion():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    write_sources_config(config_path)
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=BrokenHttpClient(),
        )
    )

    response = client.post(
        "/sources/ingest",
        json={"category": "injury", "source_name": "manual-injury"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["source_name"] == "manual-injury"
    assert body["results"][0]["status"] == "failed"
    assert "network blocked" in body["results"][0]["message"]
