import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.data_sources import (
    EspnScoreboardDataSourceAdapter,
    HttpWebpageDataSourceAdapter,
    SourceCategory,
    WorldFootballEloDataSourceAdapter,
)
from app.main import create_app
from app.source_config import SourceDefinition
from app.source_ingestion import ingest_source
from app.source_snapshot_repository import InMemorySourceSnapshotRepository


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


class UrlMappedHttpClient:
    def __init__(self, content_by_url: dict[str, bytes]):
        self.content_by_url = content_by_url
        self.requested_urls = []

    def get(self, url, timeout, headers=None):
        self.requested_urls.append(url)
        return FakeResponse(self.content_by_url[url])


class RedirectRequiredHttpClient:
    def get(self, url, timeout, headers=None, follow_redirects=False):
        if not follow_redirects:
            raise RuntimeError("redirects disabled")
        return FakeResponse(b"<html><body>Brazil 1.85 Draw 3.40 Croatia 4.20</body></html>")


class WafThenDefaultHttpClient:
    def __init__(self):
        self.calls = []

    def get(self, url, timeout, headers=None, follow_redirects=False):
        self.calls.append({"headers": headers, "follow_redirects": follow_redirects})
        if headers:
            return FakeResponse(b"<html><script>window.awsWafCookieDomainList=[]</script></html>")
        return FakeResponse(
            b'<html><body><a data-resource-id="AthleteName" href="/soccer/player/_/id/132948/neymar">Neymar</a></body></html>'
        )


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


def espn_completed_scoreboard_payload() -> bytes:
    return json.dumps(
        {
            "events": [
                {
                    "id": "401752999",
                    "date": "2026-06-20T19:00Z",
                    "name": "Brazil vs Croatia",
                    "status": {"type": {"description": "Final"}},
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {"displayName": "Brazil"},
                                    "score": "2",
                                },
                                {
                                    "homeAway": "away",
                                    "team": {"displayName": "Croatia"},
                                    "score": "1",
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


def write_two_injury_source_config(path: Path):
    path.write_text(
        json.dumps(
            {
                "schedule": [
                    {
                        "name": "manual-schedule",
                        "url": "https://data-source.example/schedule.json",
                        "priority": 1,
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
                        "name": "injury-primary",
                        "url": "https://data-source.example/injury-primary.html",
                        "priority": 1,
                        "adapter": "webpage",
                    },
                    {
                        "name": "injury-secondary",
                        "url": "https://data-source.example/injury-secondary.html",
                        "priority": 2,
                        "adapter": "webpage",
                    },
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
    assert result.facts[0].fact_type == "fixture_kickoff"
    assert result.facts[0].entity_key == "Mexico vs Canada"


def test_espn_scoreboard_adapter_extracts_team_form_facts_for_completed_matches():
    tmp_path = workspace_tmp()
    adapter = EspnScoreboardDataSourceAdapter(
        source_name="espn-world-cup-scoreboard-form",
        url="https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
        category=SourceCategory.TEAM_FORM,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(espn_completed_scoreboard_payload()),
    )

    result = adapter.ingest_schedule()

    assert result.category == SourceCategory.TEAM_FORM
    assert result.item_count == 1
    assert {fact.fact_type for fact in result.facts} == {
        "team_match_goals_for",
        "team_match_goals_against",
        "team_match_result",
    }
    assert ("team_match_goals_for", "Brazil") in {
        (fact.fact_type, fact.entity_key) for fact in result.facts
    }
    assert next(
        fact
        for fact in result.facts
        if fact.fact_type == "team_match_result" and fact.entity_key == "Brazil"
    ).value == "win"


def test_webpage_adapter_saves_html_snapshot_and_extracts_injury_facts():
    tmp_path = workspace_tmp()
    http_client = FakeHttpClient(
        b"<html><title>World Cup injuries</title><body>Neymar is doubtful. Vinicius Junior suspended.</body></html>"
    )
    adapter = HttpWebpageDataSourceAdapter(
        source_name="transfermarkt-world-cup-2026-injuries",
        url="https://www.transfermarkt.com/world-cup-2026/verletztespieler/pokalwettbewerb/WM26",
        category=SourceCategory.INJURY,
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    )

    result = adapter.ingest_snapshot()

    assert result.status == "ingested"
    assert result.item_count == 2
    assert result.snapshot is not None
    assert result.snapshot.path.suffix == ".html"
    assert result.facts[0].fact_type == "injury_availability"
    assert result.facts[0].entity_key == "Neymar"
    assert result.facts[0].value == "doubtful"


def test_webpage_adapter_extracts_injury_feed_signal_when_player_status_is_missing():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="bbc-world-cup-football-injuries",
        url="https://www.bbc.com/sport/football/world-cup",
        category=SourceCategory.INJURY,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>World Cup injury latest: two injury concerns before kickoff.</body></html>"
        ),
    ).ingest_snapshot()

    assert result.item_count == 1
    assert result.facts[0].fact_type == "injury_feed_signal"
    assert result.facts[0].entity_key == "bbc-world-cup-football-injuries"
    assert result.facts[0].value == 2


def test_webpage_adapter_extracts_team_unavailable_player_count():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="bbc-world-cup-football-injuries",
        url="https://www.bbc.com/sport/football/world-cup",
        category=SourceCategory.INJURY,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>Brazil: Neymar doubtful, Vinicius Junior suspended. Croatia: Modric available.</body></html>"
        ),
    ).ingest_snapshot()

    assert ("team_unavailable_player_count", "Brazil", 2) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_unavailable_player_count", "Croatia", 0) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_webpage_adapter_extracts_odds_news_sentiment_and_player_facts():
    tmp_path = workspace_tmp()

    odds_result = HttpWebpageDataSourceAdapter(
        source_name="oddschecker-world-cup",
        url="https://www.oddschecker.com/football/world-cup",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(b"<html><body>Brazil 1.85 Draw 3.40 Croatia 4.20</body></html>"),
    ).ingest_snapshot()
    news_result = HttpWebpageDataSourceAdapter(
        source_name="bbc-world-cup-football",
        url="https://www.bbc.com/sport/football/world-cup",
        category=SourceCategory.NEWS_SENTIMENT,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(b"<html><body>Brazil injury concern but Morocco confident</body></html>"),
    ).ingest_snapshot()
    player_result = HttpWebpageDataSourceAdapter(
        source_name="fifa-world-cup-teams",
        url="https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/teams",
        category=SourceCategory.PLAYER,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(b"<html><body>Squad: Neymar, Vinicius Junior</body></html>"),
    ).ingest_snapshot()

    assert odds_result.facts[0].fact_type == "decimal_odds"
    assert odds_result.facts[0].entity_key == "Brazil"
    assert odds_result.facts[0].value == 1.85
    assert news_result.facts[0].fact_type == "news_sentiment"
    assert news_result.facts[0].value == "negative"
    assert player_result.facts[0].fact_type == "player_presence"
    assert player_result.facts[0].entity_key == "Neymar"


def test_webpage_adapter_extracts_team_listed_player_count_from_squad_text():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="fifa-world-cup-teams",
        url="https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/teams",
        category=SourceCategory.PLAYER,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>Brazil squad: Neymar, Vinicius Junior, Alisson</body></html>"
        ),
    ).ingest_snapshot()

    assert ("team_listed_player_count", "Brazil", 3) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_webpage_adapter_extracts_espn_squad_player_facts():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="espn-brazil-squad",
        url="https://www.espn.com/soccer/team/squad/_/id/205/brazil",
        category=SourceCategory.PLAYER,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b'<html><body><a data-resource-id="AthleteName" href="/soccer/player/_/id/132948/neymar">Neymar</a></body></html>'
        ),
    ).ingest_snapshot()

    assert result.item_count == 2
    assert result.facts[0].fact_type == "player_presence"
    assert result.facts[0].entity_key == "Neymar"
    assert result.facts[0].value == "listed"


def test_webpage_adapter_extracts_team_listed_player_count_from_espn_squad_source_name():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="espn-brazil-squad",
        url="https://www.espn.com/soccer/team/squad/_/id/205/brazil",
        category=SourceCategory.PLAYER,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body>
              <a data-resource-id="AthleteName">Neymar</a>
              <a data-resource-id="AthleteName">Vinicius Junior</a>
            </body></html>
            """
        ),
    ).ingest_snapshot()

    assert ("team_listed_player_count", "Brazil", 2) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_webpage_adapter_retries_without_browser_headers_when_waf_page_is_returned():
    tmp_path = workspace_tmp()
    http_client = WafThenDefaultHttpClient()
    result = HttpWebpageDataSourceAdapter(
        source_name="espn-brazil-squad",
        url="https://www.espn.com/soccer/team/squad/_/id/205/brazil",
        category=SourceCategory.PLAYER,
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    ).ingest_snapshot()

    assert len(http_client.calls) == 2
    assert http_client.calls[0]["headers"] is not None
    assert http_client.calls[1]["headers"] is None
    assert result.facts[0].entity_key == "Neymar"


def test_webpage_adapter_follows_redirects_for_market_pages():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="oddsportal-world-cup",
        url="https://www.oddsportal.com/football/world/world-cup/",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=RedirectRequiredHttpClient(),
    ).ingest_snapshot()

    assert result.status == "ingested"
    assert result.facts[0].fact_type == "decimal_odds"


def test_webpage_adapter_extracts_market_price_fallback_when_team_names_are_missing():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="betexplorer-world-cup",
        url="https://www.betexplorer.com/football/world/world-cup/",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body><span>1.68</span><span>3.75</span><span>5.21</span></body></html>"
        ),
    ).ingest_snapshot()

    assert result.item_count == 3
    assert result.facts[0].fact_type == "market_decimal_odds"
    assert result.facts[0].entity_key == "market_price_1"
    assert result.facts[0].value == 1.68


def test_webpage_adapter_extracts_match_line_one_x_two_odds():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="betexplorer-world-cup",
        url="https://www.betexplorer.com/football/world/world-cup/",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>Brazil v Croatia 1.80 3.40 4.20</body></html>"
        ),
    ).ingest_snapshot()

    assert result.item_count == 3
    assert [
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    ] == [
        ("decimal_odds", "Brazil", 1.80),
        ("match_draw_decimal_odds", "Brazil vs Croatia", 3.40),
        ("decimal_odds", "Croatia", 4.20),
    ]


def test_webpage_adapter_extracts_market_prices_from_embedded_script_data():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="betexplorer-world-cup",
        url="https://www.betexplorer.com/football/world/world-cup/",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><script>window.odds=[1.68,3.75,5.21]</script><body>No static odds</body></html>"
        ),
    ).ingest_snapshot()

    assert result.item_count == 3
    assert [fact.value for fact in result.facts] == [1.68, 3.75, 5.21]


def test_webpage_adapter_extracts_ranking_facts():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="world-football-elo-ranking",
        url="https://www.eloratings.net/",
        category=SourceCategory.RANKING,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>1 Argentina 2145 2 France 2098 3 Brazil 2082</body></html>"
        ),
    ).ingest_snapshot()

    assert result.item_count == 6
    assert ("team_ranking_position", "Argentina", 1) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_rating", "Brazil", 2082.0) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_webpage_ranking_parser_ignores_calendar_date_fragments():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="fifa-men-ranking",
        url="https://inside.fifa.com/fifa-world-ranking/men",
        category=SourceCategory.RANKING,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>11 June 2026 20 July 2026 3 Brazil 2082</body></html>"
        ),
    ).ingest_snapshot()

    assert {fact.entity_key for fact in result.facts} == {"Brazil"}


def test_world_football_elo_adapter_extracts_team_ratings_from_tsv_files():
    tmp_path = workspace_tmp()
    http_client = UrlMappedHttpClient(
        {
            "https://www.eloratings.net/World.tsv": (
                b"7\t7\tBR\t1978\t1\t2195\n12\t12\tHR\t1912\t4\t2015\n"
            ),
            "https://www.eloratings.net/en.teams.tsv": (
                b"BR\tBrazil\nHR\tCroatia\n"
            ),
        }
    )
    result = WorldFootballEloDataSourceAdapter(
        source_name="world-football-elo-ranking",
        url="https://www.eloratings.net/",
        category=SourceCategory.RANKING,
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    ).ingest_rankings()

    assert http_client.requested_urls == [
        "https://www.eloratings.net/World.tsv",
        "https://www.eloratings.net/en.teams.tsv",
    ]
    assert result.status == "ingested"
    assert result.snapshot is not None
    assert result.snapshot.path.suffix == ".json"
    assert ("team_ranking_position", "Brazil", 7) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_rating", "Croatia", 1912.0) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_source_ingestion_routes_world_football_elo_adapter():
    tmp_path = workspace_tmp()
    http_client = UrlMappedHttpClient(
        {
            "https://www.eloratings.net/World.tsv": b"7\t7\tBR\t1978\n",
            "https://www.eloratings.net/en.teams.tsv": b"BR\tBrazil\n",
        }
    )

    result = ingest_source(
        SourceDefinition(
            category=SourceCategory.RANKING,
            name="world-football-elo-ranking",
            url="https://www.eloratings.net/",
            priority=2,
            adapter="world_football_elo",
        ),
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    )

    assert result.status == "ingested"
    assert result.facts[0].entity_key == "Brazil"


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


def test_sources_api_records_snapshot_metadata():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    write_sources_config(config_path)
    repository = InMemorySourceSnapshotRepository()
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=FakeHttpClient(espn_scoreboard_payload()),
            source_snapshot_repository=repository,
        )
    )

    response = client.post(
        "/sources/ingest",
        json={"category": "schedule", "source_name": "espn-world-cup-scoreboard"},
    )

    assert response.status_code == 200
    metadata = repository.list_recent()
    assert len(metadata) == 1
    assert metadata[0].source_name == "espn-world-cup-scoreboard"
    assert metadata[0].category == "schedule"
    assert metadata[0].status == "ingested"
    assert metadata[0].path.endswith(".json")
    assert metadata[0].content_hash
    assert metadata[0].item_count == 1
    assert metadata[0].fact_count == 1
    assert metadata[0].match_count == 1


def test_sources_api_lists_recorded_snapshot_metadata():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    write_sources_config(config_path)
    repository = InMemorySourceSnapshotRepository()
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=FakeHttpClient(espn_scoreboard_payload()),
            source_snapshot_repository=repository,
        )
    )
    client.post(
        "/sources/ingest",
        json={"category": "schedule", "source_name": "espn-world-cup-scoreboard"},
    )

    response = client.get("/sources/snapshots")

    assert response.status_code == 200
    body = response.json()
    assert body["snapshots"][0]["source_name"] == "espn-world-cup-scoreboard"
    assert body["snapshots"][0]["category"] == "schedule"
    assert body["snapshots"][0]["status"] == "ingested"


def test_sources_api_ingests_configured_webpage_snapshot_with_normalized_facts():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    write_sources_config(config_path)
    http_client = FakeHttpClient(b"<html><body>Neymar is doubtful</body></html>")
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
    assert body["results"][0]["facts"][0]["fact_type"] == "injury_availability"
    assert body["results"][0]["facts"][0]["entity_key"] == "Neymar"
    assert body["results"][0]["facts"][0]["value"] == "doubtful"


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


def test_sources_validate_api_cross_checks_facts_by_source_priority():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    write_two_injury_source_config(config_path)
    http_client = UrlMappedHttpClient(
        {
            "https://data-source.example/injury-primary.html": (
                b"<html><body>Neymar is doubtful</body></html>"
            ),
            "https://data-source.example/injury-secondary.html": (
                b"<html><body>Neymar is available</body></html>"
            ),
        }
    )
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=http_client,
        )
    )

    response = client.post("/sources/validate", json={"category": "injury"})

    assert response.status_code == 200
    body = response.json()
    assert [result["status"] for result in body["results"]] == ["ingested", "ingested"]
    assert body["validated_facts"][0]["fact_type"] == "injury_availability"
    assert body["validated_facts"][0]["entity_key"] == "Neymar"
    assert body["validated_facts"][0]["status"] == "conflicting"
    assert body["validated_facts"][0]["value"] == "doubtful"
    assert body["validated_facts"][0]["sources"] == [
        "injury-primary",
        "injury-secondary",
    ]
