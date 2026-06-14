import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.data_sources import (
    BetExplorerOddsDataSourceAdapter,
    EspnScoreboardDataSourceAdapter,
    EspnTeamRosterDiscoveryDataSourceAdapter,
    EspnTeamScheduleDiscoveryDataSourceAdapter,
    FifaRankingDataSourceAdapter,
    HttpWebpageDataSourceAdapter,
    OddsCheckerOddsDataSourceAdapter,
    SportsMoleInjuryDataSourceAdapter,
    SourceCategory,
    TransfermarktInjuryDataSourceAdapter,
    TransfermarktSquadDataSourceAdapter,
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


def test_espn_scoreboard_adapter_extracts_team_form_from_score_objects():
    tmp_path = workspace_tmp()
    payload = {
        "events": [
            {
                "id": "760419",
                "date": "2026-06-13T22:00Z",
                "status": {"type": {"description": "Full Time"}},
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "team": {"displayName": "Brazil"},
                                "score": {"value": 1.0, "displayValue": "1"},
                            },
                            {
                                "homeAway": "away",
                                "team": {"displayName": "Morocco"},
                                "score": {"value": 1.0, "displayValue": "1"},
                            },
                        ]
                    }
                ],
            }
        ]
    }
    adapter = EspnScoreboardDataSourceAdapter(
        source_name="espn-brazil-team-schedule",
        url="https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/205/schedule",
        category=SourceCategory.TEAM_FORM,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(json.dumps(payload).encode()),
    )

    result = adapter.ingest_schedule()

    assert ("team_match_goals_for", "Brazil", 1) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_match_goals_against", "Morocco", 1) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_match_result", "Brazil", "draw") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_espn_scoreboard_adapter_reads_competition_level_status():
    tmp_path = workspace_tmp()
    payload = {
        "events": [
            {
                "id": "760419",
                "date": "2026-06-13T22:00Z",
                "competitions": [
                    {
                        "status": {"type": {"description": "Full Time"}},
                        "competitors": [
                            {
                                "homeAway": "home",
                                "team": {"displayName": "Brazil"},
                                "score": {"displayValue": "1"},
                            },
                            {
                                "homeAway": "away",
                                "team": {"displayName": "Morocco"},
                                "score": {"displayValue": "1"},
                            },
                        ],
                    }
                ],
            }
        ]
    }
    adapter = EspnScoreboardDataSourceAdapter(
        source_name="espn-brazil-team-schedule",
        url="https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/205/schedule",
        category=SourceCategory.TEAM_FORM,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(json.dumps(payload).encode()),
    )

    result = adapter.ingest_schedule()

    assert result.matches[0].status == "Full Time"
    assert ("team_match_result", "Brazil", "draw") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_espn_scoreboard_team_form_keeps_latest_completed_match_per_team():
    tmp_path = workspace_tmp()
    payload = {
        "events": [
            {
                "id": "older",
                "date": "2026-06-10T22:00Z",
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
                                "team": {"displayName": "Morocco"},
                                "score": "0",
                            },
                        ]
                    }
                ],
            },
            {
                "id": "newer",
                "date": "2026-06-13T22:00Z",
                "status": {"type": {"description": "Full Time"}},
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "team": {"displayName": "Brazil"},
                                "score": {"displayValue": "1"},
                            },
                            {
                                "homeAway": "away",
                                "team": {"displayName": "Morocco"},
                                "score": {"displayValue": "1"},
                            },
                        ]
                    }
                ],
            },
        ]
    }
    adapter = EspnScoreboardDataSourceAdapter(
        source_name="espn-brazil-team-schedule",
        url="https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/205/schedule",
        category=SourceCategory.TEAM_FORM,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(json.dumps(payload).encode()),
    )

    result = adapter.ingest_schedule()
    brazil_facts = [
        (fact.fact_type, fact.value)
        for fact in result.facts
        if fact.entity_key == "Brazil"
    ]

    assert ("team_match_goals_for", 1) in brazil_facts
    assert ("team_match_result", "draw") in brazil_facts
    assert ("team_match_goals_for", 2) not in brazil_facts


def test_espn_team_schedule_discovery_fetches_team_schedules_from_team_index():
    tmp_path = workspace_tmp()
    teams_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams"
    brazil_schedule_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/205/schedule"
    morocco_schedule_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/2869/schedule"
    teams_payload = {
        "sports": [
            {
                "leagues": [
                    {
                        "teams": [
                            {"team": {"id": "205", "displayName": "Brazil"}},
                            {"team": {"id": "2869", "displayName": "Morocco"}},
                        ]
                    }
                ]
            }
        ]
    }
    schedule_payload = {
        "events": [
            {
                "id": "760419",
                "date": "2026-06-13T22:00Z",
                "competitions": [
                    {
                        "status": {"type": {"description": "Full Time"}},
                        "competitors": [
                            {
                                "homeAway": "home",
                                "team": {"displayName": "Brazil"},
                                "score": {"displayValue": "1"},
                            },
                            {
                                "homeAway": "away",
                                "team": {"displayName": "Morocco"},
                                "score": {"displayValue": "1"},
                            },
                        ],
                    }
                ],
            }
        ]
    }
    http_client = UrlMappedHttpClient(
        {
            teams_url: json.dumps(teams_payload).encode(),
            brazil_schedule_url: json.dumps(schedule_payload).encode(),
            morocco_schedule_url: json.dumps(schedule_payload).encode(),
        }
    )

    result = EspnTeamScheduleDiscoveryDataSourceAdapter(
        source_name="espn-world-cup-team-schedules",
        url=teams_url,
        category=SourceCategory.TEAM_FORM,
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    ).ingest_team_form()

    assert http_client.requested_urls == [
        teams_url,
        brazil_schedule_url,
        morocco_schedule_url,
    ]
    assert result.status == "ingested"
    assert result.item_count == 2
    assert result.snapshot is not None
    assert result.snapshot.path.suffix == ".json"
    assert ("team_match_goals_for", "Brazil", 1) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_match_result", "Morocco", "draw") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_espn_team_schedule_discovery_reuses_fresh_snapshot_cache():
    tmp_path = workspace_tmp()
    teams_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams"
    schedule_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/205/schedule"
    http_client = UrlMappedHttpClient(
        {
            teams_url: json.dumps(
                {
                    "sports": [
                        {
                            "leagues": [
                                {
                                    "teams": [
                                        {"team": {"id": "205", "displayName": "Brazil"}}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ).encode(),
            schedule_url: json.dumps(
                {
                    "events": [
                        {
                            "id": "760419",
                            "date": "2026-06-13T22:00Z",
                            "competitions": [
                                {
                                    "status": {"type": {"description": "Full Time"}},
                                    "competitors": [
                                        {
                                            "homeAway": "home",
                                            "team": {"displayName": "Brazil"},
                                            "score": {"displayValue": "1"},
                                        },
                                        {
                                            "homeAway": "away",
                                            "team": {"displayName": "Morocco"},
                                            "score": {"displayValue": "1"},
                                        },
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ).encode(),
        }
    )
    snapshot_dir = tmp_path / "snapshots"
    first = EspnTeamScheduleDiscoveryDataSourceAdapter(
        source_name="espn-world-cup-team-schedules",
        url=teams_url,
        category=SourceCategory.TEAM_FORM,
        snapshot_dir=snapshot_dir,
        http_client=http_client,
    ).ingest_team_form()

    second = EspnTeamScheduleDiscoveryDataSourceAdapter(
        source_name="espn-world-cup-team-schedules",
        url=teams_url,
        category=SourceCategory.TEAM_FORM,
        snapshot_dir=snapshot_dir,
        http_client=BrokenHttpClient(),
    ).ingest_team_form()

    assert second.snapshot == first.snapshot
    assert second.facts == first.facts


def test_webpage_schedule_adapter_extracts_schema_org_sports_events():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="oddsportal-world-cup-schedule",
        url="https://www.oddsportal.com/football/world/world-championship-2026/",
        category=SourceCategory.SCHEDULE,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body>
              <script type="application/ld+json">
              {
                "@context": "https://schema.org",
                "@type": ["Event", "SportsEvent"],
                "sport": "football",
                "name": "Haiti - Scotland",
                "startDate": "2026-06-14T03:00:00+02:00"
              }
              </script>
              <script type="application/ld+json">
              {
                "@context": "https://schema.org",
                "@type": ["Event", "SportsEvent"],
                "sport": "football",
                "name": "Brazil - Morocco",
                "startDate": "2026-06-14T00:00:00+02:00"
              }
              </script>
            </body></html>
            """
        ),
    ).ingest_snapshot()

    assert result.status == "ingested"
    assert result.item_count == 2
    assert [
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    ] == [
        ("fixture_kickoff", "Haiti vs Scotland", "2026-06-14T03:00:00+02:00"),
        ("fixture_kickoff", "Brazil vs Morocco", "2026-06-14T00:00:00+02:00"),
    ]


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


def test_sportsmole_injury_adapter_crawls_articles_and_extracts_team_sections():
    tmp_path = workspace_tmp()
    listing_url = "https://www.sportsmole.co.uk/football/world-cup-2026/injuries-and-suspensions.html"
    article_url = (
        "https://www.sportsmole.co.uk/football/sweden/world-cup-2026/team-news/"
        "sweden-vs-tunisia-injury-suspension-list-predicted-xis_599053.html"
    )
    http_client = UrlMappedHttpClient(
        {
            listing_url: f"""
            <html><body>
              <a href="/football/sweden/world-cup-2026/team-news/sweden-vs-tunisia-injury-suspension-list-predicted-xis_599053.html">
                Sweden vs. Tunisia injury, suspension list, predicted XIs
              </a>
            </body></html>
            """.encode(),
            article_url: b"""
            <html><body>
              <h2><a href="/football/world-cup/sweden-vs-tunisia_game_248733.html">SWEDEN vs. TUNISIA</a></h2>
              <h2>SWEDEN</h2>
              <p><strong>Out:&nbsp;</strong>None</p>
              <p><strong>Doubtful:&nbsp;</strong><a href="/people/gabriel-gudmundsson/">Gabriel Gudmundsson</a> (illness)</p>
              <h2>TUNISIA</h2>
              <p><strong>Out:&nbsp;</strong>None</p>
              <p><strong>Doubtful:&nbsp;</strong>None</p>
            </body></html>
            """,
        }
    )

    result = SportsMoleInjuryDataSourceAdapter(
        source_name="sportsmole-world-cup-injuries",
        url=listing_url,
        category=SourceCategory.INJURY,
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    ).ingest_injuries()

    assert http_client.requested_urls == [listing_url, article_url]
    assert result.status == "ingested"
    assert result.item_count == 1
    assert (
        "injury_availability",
        "Gabriel Gudmundsson",
        "doubtful",
    ) in {(fact.fact_type, fact.entity_key, fact.value) for fact in result.facts}
    assert (
        "team_unavailable_player_count",
        "Sweden",
        1,
    ) in {(fact.fact_type, fact.entity_key, fact.value) for fact in result.facts}
    assert (
        "team_unavailable_player_count",
        "Tunisia",
        0,
    ) in {(fact.fact_type, fact.entity_key, fact.value) for fact in result.facts}


def test_transfermarkt_injury_adapter_extracts_rows_and_team_counts():
    tmp_path = workspace_tmp()
    url = "https://www.transfermarkt.com/world-cup-2026/verletztespieler/pokalwettbewerb/WM26"
    result = TransfermarktInjuryDataSourceAdapter(
        source_name="transfermarkt-world-cup-2026-injuries",
        url=url,
        category=SourceCategory.INJURY,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body><table>
              <tr>
                <td class="hauptlink"><a title="Neymar" href="/neymar/profil/spieler/68290">Neymar</a></td>
                <td><img title="Brazil" alt="Brazil" /></td>
                <td>Muscle injury</td>
              </tr>
              <tr>
                <td class="hauptlink"><a href="/vinicius-junior/profil/spieler/371998">Vinicius Junior</a></td>
                <td><img title="Brazil" alt="Brazil" /></td>
                <td>Suspended</td>
              </tr>
              <tr>
                <td class="hauptlink"><a href="/luka-modric/profil/spieler/27992">Luka Modric</a></td>
                <td><img title="Croatia" alt="Croatia" /></td>
                <td>Doubtful</td>
              </tr>
            </table></body></html>
            """
        ),
    ).ingest_injuries()

    assert result.status == "ingested"
    assert result.item_count == 3
    assert (
        "injury_availability",
        "Neymar",
        "injured",
    ) in {(fact.fact_type, fact.entity_key, fact.value) for fact in result.facts}
    assert (
        "injury_availability",
        "Vinicius Junior",
        "suspended",
    ) in {(fact.fact_type, fact.entity_key, fact.value) for fact in result.facts}
    assert (
        "team_unavailable_player_count",
        "Brazil",
        2,
    ) in {(fact.fact_type, fact.entity_key, fact.value) for fact in result.facts}
    assert (
        "team_unavailable_player_count",
        "Croatia",
        1,
    ) in {(fact.fact_type, fact.entity_key, fact.value) for fact in result.facts}


def test_webpage_adapter_does_not_treat_look_out_copy_as_injury_absence():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="bbc-world-cup-football-injuries",
        url="https://www.bbc.com/sport/football/world-cup",
        category=SourceCategory.INJURY,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>Who are the Haiti players to look out for against Scotland?</body></html>"
        ),
    ).ingest_snapshot()

    assert result.facts == ()


def test_webpage_adapter_does_not_treat_article_title_colon_as_team_injury_segment():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="bbc-world-cup-football-injuries",
        url="https://www.bbc.com/sport/football/world-cup",
        category=SourceCategory.INJURY,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>Superstar in Spain, doubted in Brazil: Will Vinicius Jr convince a nation? Who are the Haiti players to look out for?</body></html>"
        ),
    ).ingest_snapshot()

    assert result.facts == ()


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
    assert ("team_news_sentiment", "Brazil", "negative") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in news_result.facts
    }
    assert ("team_news_sentiment", "Morocco", "positive") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in news_result.facts
    }
    assert player_result.facts[0].fact_type == "player_presence"
    assert player_result.facts[0].entity_key == "Neymar"


def test_webpage_adapter_extracts_team_news_sentiment_from_team_segments():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="bbc-world-cup-football",
        url="https://www.bbc.com/sport/football/world-cup",
        category=SourceCategory.NEWS_SENTIMENT,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>Brazil: confident boost. Croatia: injury concern pressure.</body></html>"
        ),
    ).ingest_snapshot()

    assert ("team_news_sentiment", "Brazil", "positive") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_news_sentiment", "Croatia", "negative") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_webpage_adapter_ignores_lowercase_news_colon_fragments_as_team_sentiment():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="bbc-world-cup-football",
        url="https://www.bbc.com/sport/football/world-cup",
        category=SourceCategory.NEWS_SENTIMENT,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>debate the long-asked question: injury pressure. Brazil: confident boost.</body></html>"
        ),
    ).ingest_snapshot()

    assert ("team_news_sentiment", "Brazil", "positive") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert "debate the long-asked question" not in {
        fact.entity_key for fact in result.facts if fact.fact_type == "team_news_sentiment"
    }


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


def test_espn_team_roster_discovery_fetches_rosters_from_team_index():
    tmp_path = workspace_tmp()
    teams_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams"
    brazil_roster_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/205/roster"
    morocco_roster_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/2869/roster"
    teams_payload = {
        "sports": [
            {
                "leagues": [
                    {
                        "teams": [
                            {"team": {"id": "205", "displayName": "Brazil"}},
                            {"team": {"id": "2869", "displayName": "Morocco"}},
                        ]
                    }
                ]
            }
        ]
    }
    http_client = UrlMappedHttpClient(
        {
            teams_url: json.dumps(teams_payload).encode(),
            brazil_roster_url: json.dumps(
                {
                    "athletes": [
                        {"displayName": "Neymar"},
                        {"fullName": "Vinicius Junior"},
                    ]
                }
            ).encode(),
            morocco_roster_url: json.dumps(
                {
                    "athletes": [
                        {"displayName": "Achraf Hakimi"},
                    ]
                }
            ).encode(),
        }
    )

    result = EspnTeamRosterDiscoveryDataSourceAdapter(
        source_name="espn-world-cup-rosters",
        url=teams_url,
        category=SourceCategory.PLAYER,
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    ).ingest_players()

    assert http_client.requested_urls == [
        teams_url,
        brazil_roster_url,
        morocco_roster_url,
    ]
    assert result.status == "ingested"
    assert result.item_count == 2
    assert ("player_presence", "Neymar", "listed") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("player_presence", "Achraf Hakimi", "listed") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_listed_player_count", "Brazil", 2) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_listed_player_count", "Morocco", 1) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_espn_team_roster_discovery_reuses_fresh_snapshot_cache():
    tmp_path = workspace_tmp()
    teams_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams"
    roster_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/205/roster"
    http_client = UrlMappedHttpClient(
        {
            teams_url: json.dumps(
                {
                    "sports": [
                        {
                            "leagues": [
                                {
                                    "teams": [
                                        {"team": {"id": "205", "displayName": "Brazil"}}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ).encode(),
            roster_url: json.dumps(
                {
                    "athletes": [
                        {"displayName": "Neymar"},
                    ]
                }
            ).encode(),
        }
    )
    snapshot_dir = tmp_path / "snapshots"
    first = EspnTeamRosterDiscoveryDataSourceAdapter(
        source_name="espn-world-cup-rosters",
        url=teams_url,
        category=SourceCategory.PLAYER,
        snapshot_dir=snapshot_dir,
        http_client=http_client,
    ).ingest_players()

    second = EspnTeamRosterDiscoveryDataSourceAdapter(
        source_name="espn-world-cup-rosters",
        url=teams_url,
        category=SourceCategory.PLAYER,
        snapshot_dir=snapshot_dir,
        http_client=BrokenHttpClient(),
    ).ingest_players()

    assert second.snapshot == first.snapshot
    assert second.facts == first.facts


def test_transfermarkt_squad_adapter_extracts_player_rows_and_team_counts():
    tmp_path = workspace_tmp()
    result = TransfermarktSquadDataSourceAdapter(
        source_name="transfermarkt-world-cup-2026-squads",
        url="https://www.transfermarkt.com/world-cup-2026/teilnehmer/pokalwettbewerb/WM26",
        category=SourceCategory.PLAYER,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body><table>
              <tr>
                <td class="hauptlink"><a title="Neymar" href="/neymar/profil/spieler/68290">Neymar</a></td>
                <td><img title="Brazil" alt="Brazil" /></td>
              </tr>
              <tr>
                <td class="hauptlink"><a href="/vinicius-junior/profil/spieler/371998">Vinicius Junior</a></td>
                <td><img title="Brazil" alt="Brazil" /></td>
              </tr>
              <tr>
                <td class="hauptlink"><a href="/achraf-hakimi/profil/spieler/398073">Achraf Hakimi</a></td>
                <td><img title="Morocco" alt="Morocco" /></td>
              </tr>
            </table></body></html>
            """
        ),
    ).ingest_players()

    assert result.status == "ingested"
    assert result.item_count == 3
    assert ("player_presence", "Neymar", "listed") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("player_presence", "Achraf Hakimi", "listed") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_listed_player_count", "Brazil", 2) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_listed_player_count", "Morocco", 1) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_transfermarkt_squad_adapter_deduplicates_repeated_player_rows():
    tmp_path = workspace_tmp()
    result = TransfermarktSquadDataSourceAdapter(
        source_name="transfermarkt-world-cup-2026-squads",
        url="https://www.transfermarkt.com/world-cup-2026/teilnehmer/pokalwettbewerb/WM26",
        category=SourceCategory.PLAYER,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body><table>
              <tr>
                <td><a href="/neymar/profil/spieler/68290">Neymar</a></td>
                <td><img title="Brazil" /></td>
              </tr>
              <tr>
                <td><a href="/neymar/profil/spieler/68290">Neymar</a></td>
                <td><img title="Brazil" /></td>
              </tr>
            </table></body></html>
            """
        ),
    ).ingest_players()

    assert [
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    ] == [
        ("player_presence", "Neymar", "listed"),
        ("team_listed_player_count", "Brazil", 1),
    ]


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


def test_webpage_adapter_extracts_betexplorer_match_row_one_x_two_odds():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="betexplorer-world-cup",
        url="https://www.betexplorer.com/football/world/world-cup/",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body>
              <li class="showHide table-main__tournamentLiContent" data-event-id="b5JayTEd">
                <a href="/football/world/world-championship-2026/brazil-morocco/b5JayTEd/">
                  <div class="table-main__participantHome"><p>Brazil</p></div>
                  <div class="table-main__participantAway"><p>Morocco</p></div>
                </a>
                <div class="table-main__oddsLi oddsColumn">
                  <p data-odd="1.68" data-odd-max="1.72"></p>
                  <p data-odd="3.73" data-odd-max="3.90"></p>
                  <p data-odd="5.52" data-odd-max="6.00"></p>
                </div>
              </li>
            </body></html>
            """
        ),
    ).ingest_snapshot()

    assert result.item_count == 3
    assert [
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    ] == [
        ("decimal_odds", "Brazil", 1.68),
        ("match_draw_decimal_odds", "Brazil vs Morocco", 3.73),
        ("decimal_odds", "Morocco", 5.52),
    ]


def test_betexplorer_adapter_extracts_match_row_one_x_two_odds():
    tmp_path = workspace_tmp()
    result = BetExplorerOddsDataSourceAdapter(
        source_name="betexplorer-world-cup",
        url="https://www.betexplorer.com/football/world/world-cup/",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body>
              <li class="showHide table-main__tournamentLiContent" data-event-id="b5JayTEd">
                <a href="/football/world/world-championship-2026/brazil-morocco/b5JayTEd/">
                  <div class="table-main__participantHome"><p>Brazil</p></div>
                  <div class="table-main__participantAway"><p>Morocco</p></div>
                </a>
                <div class="table-main__oddsLi oddsColumn">
                  <p data-odd="1.68"></p>
                  <p data-odd="3.73"></p>
                  <p data-odd="5.52"></p>
                </div>
              </li>
            </body></html>
            """
        ),
    ).ingest_odds()

    assert result.status == "ingested"
    assert result.item_count == 3
    assert [
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    ] == [
        ("decimal_odds", "Brazil", 1.68),
        ("match_draw_decimal_odds", "Brazil vs Morocco", 3.73),
        ("decimal_odds", "Morocco", 5.52),
    ]


def test_betexplorer_adapter_keeps_market_price_fallback():
    tmp_path = workspace_tmp()
    result = BetExplorerOddsDataSourceAdapter(
        source_name="betexplorer-world-cup",
        url="https://www.betexplorer.com/football/world/world-cup/",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body><span>1.68</span><span>3.75</span><span>5.21</span></body></html>"
        ),
    ).ingest_odds()

    assert [
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    ] == [
        ("market_decimal_odds", "market_price_1", 1.68),
        ("market_decimal_odds", "market_price_2", 3.75),
        ("market_decimal_odds", "market_price_3", 5.21),
    ]


def test_oddschecker_adapter_extracts_match_card_one_x_two_odds():
    tmp_path = workspace_tmp()
    result = OddsCheckerOddsDataSourceAdapter(
        source_name="oddschecker-world-cup",
        url="https://www.oddschecker.com/football/world-cup",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body>
              <article data-testid="event-card" data-home-team="Brazil" data-away-team="Morocco">
                <button data-outcome-name="Brazil" data-odds="1.72"></button>
                <button data-outcome-name="Draw" data-odds="3.90"></button>
                <button data-outcome-name="Morocco" data-odds="5.80"></button>
              </article>
            </body></html>
            """
        ),
    ).ingest_odds()

    assert result.status == "ingested"
    assert result.item_count == 3
    assert [
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    ] == [
        ("decimal_odds", "Brazil", 1.72),
        ("match_draw_decimal_odds", "Brazil vs Morocco", 3.90),
        ("decimal_odds", "Morocco", 5.80),
    ]


def test_oddschecker_adapter_handles_fractional_prices_and_attribute_order():
    tmp_path = workspace_tmp()
    result = OddsCheckerOddsDataSourceAdapter(
        source_name="oddschecker-world-cup",
        url="https://www.oddschecker.com/football/world-cup",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body>
              <article data-testid="event-card" data-home-team="Brazil" data-away-team="Morocco">
                <button data-odds="4/5" data-outcome-name="Brazil"></button>
                <button data-odds="3/1" data-outcome-name="Draw"></button>
                <button data-odds="9/2" data-outcome-name="Morocco"></button>
              </article>
            </body></html>
            """
        ),
    ).ingest_odds()

    assert [
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    ] == [
        ("decimal_odds", "Brazil", 1.8),
        ("match_draw_decimal_odds", "Brazil vs Morocco", 4.0),
        ("decimal_odds", "Morocco", 5.5),
    ]


def test_webpage_adapter_limits_betexplorer_rows_to_world_championship_section():
    tmp_path = workspace_tmp()
    result = HttpWebpageDataSourceAdapter(
        source_name="betexplorer-world-cup",
        url="https://www.betexplorer.com/football/world/world-cup/",
        category=SourceCategory.ODDS,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body>
              <ul class="leagues-list" data-country="world">
                <a data-league-name="World Championship 2026"></a>
                <li class="showHide table-main__tournamentLiContent" data-event-id="b5JayTEd">
                  <div class="table-main__participantHome"><p>Brazil</p></div>
                  <div class="table-main__participantAway"><p>Morocco</p></div>
                  <p data-odd="1.68"></p><p data-odd="3.73"></p><p data-odd="5.52"></p>
                </li>
              </ul>
              <ul class="leagues-list" data-country="argentina">
                <a data-league-name="Primera Nacional"></a>
                <li class="showHide table-main__tournamentLiContent" data-event-id="tjQ2vYZO">
                  <div class="table-main__participantHome"><p>Gimnasia Jujuy</p></div>
                  <div class="table-main__participantAway"><p>San Martin S.J.</p></div>
                  <p data-odd="1.85"></p><p data-odd="3.20"></p><p data-odd="4.00"></p>
                </li>
              </ul>
            </body></html>
            """
        ),
    ).ingest_snapshot()

    entity_keys = {fact.entity_key for fact in result.facts}
    assert "Brazil" in entity_keys
    assert "Morocco" in entity_keys
    assert "Gimnasia Jujuy" not in entity_keys
    assert "San Martin S.J" not in entity_keys


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


def test_fifa_ranking_adapter_extracts_embedded_team_rankings():
    tmp_path = workspace_tmp()
    result = FifaRankingDataSourceAdapter(
        source_name="fifa-men-ranking",
        url="https://inside.fifa.com/fifa-world-ranking/men",
        category=SourceCategory.RANKING,
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"ranking":[
              {"rank":1,"teamName":"Argentina","totalPoints":1885.36},
              {"rank":2,"countryName":"France","points":1867.71}
            ]}}}
            </script></html>
            """
        ),
    ).ingest_rankings()

    assert result.status == "ingested"
    assert result.snapshot is not None
    assert result.snapshot.path.suffix == ".html"
    assert ("team_ranking_position", "Argentina", 1) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }
    assert ("team_rating", "France", 1867.71) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


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


def test_source_ingestion_routes_fifa_ranking_adapter():
    tmp_path = workspace_tmp()

    result = ingest_source(
        SourceDefinition(
            category=SourceCategory.RANKING,
            name="fifa-men-ranking",
            url="https://inside.fifa.com/fifa-world-ranking/men",
            priority=1,
            adapter="fifa_ranking",
        ),
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>1 Argentina 1885.36 2 France 1867.71</body></html>"
        ),
    )

    assert result.status == "ingested"
    assert result.facts[0].entity_key == "Argentina"


def test_source_ingestion_routes_espn_team_schedule_discovery_adapter():
    tmp_path = workspace_tmp()
    teams_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams"
    schedule_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/205/schedule"
    http_client = UrlMappedHttpClient(
        {
            teams_url: json.dumps(
                {
                    "sports": [
                        {
                            "leagues": [
                                {
                                    "teams": [
                                        {"team": {"id": "205", "displayName": "Brazil"}}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ).encode(),
            schedule_url: json.dumps(
                {
                    "events": [
                        {
                            "id": "760419",
                            "date": "2026-06-13T22:00Z",
                            "competitions": [
                                {
                                    "status": {"type": {"description": "Full Time"}},
                                    "competitors": [
                                        {
                                            "homeAway": "home",
                                            "team": {"displayName": "Brazil"},
                                            "score": {"displayValue": "1"},
                                        },
                                        {
                                            "homeAway": "away",
                                            "team": {"displayName": "Morocco"},
                                            "score": {"displayValue": "1"},
                                        },
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ).encode(),
        }
    )

    result = ingest_source(
        SourceDefinition(
            category=SourceCategory.TEAM_FORM,
            name="espn-world-cup-team-schedules",
            url=teams_url,
            priority=2,
            adapter="espn_team_schedules",
        ),
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    )

    assert result.status == "ingested"
    assert result.item_count == 1
    assert ("team_match_result", "Brazil", "draw") in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_source_ingestion_routes_espn_team_roster_discovery_adapter():
    tmp_path = workspace_tmp()
    teams_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams"
    roster_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/205/roster"
    http_client = UrlMappedHttpClient(
        {
            teams_url: json.dumps(
                {
                    "sports": [
                        {
                            "leagues": [
                                {
                                    "teams": [
                                        {"team": {"id": "205", "displayName": "Brazil"}}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ).encode(),
            roster_url: json.dumps(
                {
                    "athletes": [
                        {"displayName": "Neymar"},
                        {"displayName": "Alisson Becker"},
                    ]
                }
            ).encode(),
        }
    )

    result = ingest_source(
        SourceDefinition(
            category=SourceCategory.PLAYER,
            name="espn-world-cup-rosters",
            url=teams_url,
            priority=1,
            adapter="espn_team_rosters",
        ),
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    )

    assert result.status == "ingested"
    assert result.item_count == 1
    assert ("team_listed_player_count", "Brazil", 2) in {
        (fact.fact_type, fact.entity_key, fact.value) for fact in result.facts
    }


def test_source_ingestion_routes_sportsmole_injury_adapter():
    tmp_path = workspace_tmp()
    listing_url = "https://www.sportsmole.co.uk/football/world-cup-2026/injuries-and-suspensions.html"
    article_url = (
        "https://www.sportsmole.co.uk/football/sweden/world-cup-2026/team-news/"
        "sweden-vs-tunisia-injury-suspension-list-predicted-xis_599053.html"
    )
    http_client = UrlMappedHttpClient(
        {
            listing_url: (
                b'<html><body><a href="/football/sweden/world-cup-2026/team-news/'
                b'sweden-vs-tunisia-injury-suspension-list-predicted-xis_599053.html">'
                b"Sweden vs. Tunisia injury, suspension list, predicted XIs</a></body></html>"
            ),
            article_url: (
                b"<html><body><h2>SWEDEN</h2>"
                b"<p><strong>Out:&nbsp;</strong>None</p>"
                b"<p><strong>Doubtful:&nbsp;</strong>None</p></body></html>"
            ),
        }
    )

    result = ingest_source(
        SourceDefinition(
            category=SourceCategory.INJURY,
            name="sportsmole-world-cup-injuries",
            url=listing_url,
            priority=1,
            adapter="sportsmole_injuries",
        ),
        snapshot_dir=tmp_path / "snapshots",
        http_client=http_client,
    )

    assert result.status == "ingested"
    assert result.facts[0].fact_type == "team_unavailable_player_count"
    assert result.facts[0].entity_key == "Sweden"


def test_source_ingestion_routes_transfermarkt_injury_adapter():
    tmp_path = workspace_tmp()
    url = "https://www.transfermarkt.com/world-cup-2026/verletztespieler/pokalwettbewerb/WM26"

    result = ingest_source(
        SourceDefinition(
            category=SourceCategory.INJURY,
            name="transfermarkt-world-cup-2026-injuries",
            url=url,
            priority=2,
            adapter="transfermarkt_injuries",
        ),
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body><table>
              <tr>
                <td class="hauptlink"><a href="/neymar/profil/spieler/68290">Neymar</a></td>
                <td><img title="Brazil" /></td>
                <td>Knee injury</td>
              </tr>
            </table></body></html>
            """
        ),
    )

    assert result.status == "ingested"
    assert result.facts[0].fact_type == "injury_availability"
    assert result.facts[0].source_name == "transfermarkt-world-cup-2026-injuries"


def test_source_ingestion_routes_oddschecker_odds_adapter():
    tmp_path = workspace_tmp()
    url = "https://www.oddschecker.com/football/world-cup"

    result = ingest_source(
        SourceDefinition(
            category=SourceCategory.ODDS,
            name="oddschecker-world-cup",
            url=url,
            priority=3,
            adapter="oddschecker_odds",
        ),
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body>
              <article data-testid="event-card" data-home-team="Brazil" data-away-team="Morocco">
                <button data-outcome-name="Brazil" data-odds="1.72"></button>
                <button data-outcome-name="Draw" data-odds="3.90"></button>
                <button data-outcome-name="Morocco" data-odds="5.80"></button>
              </article>
            </body></html>
            """
        ),
    )

    assert result.status == "ingested"
    assert result.facts[0].fact_type == "decimal_odds"
    assert result.facts[0].source_name == "oddschecker-world-cup"


def test_source_ingestion_routes_betexplorer_odds_adapter():
    tmp_path = workspace_tmp()
    url = "https://www.betexplorer.com/football/world/world-cup/"

    result = ingest_source(
        SourceDefinition(
            category=SourceCategory.ODDS,
            name="betexplorer-world-cup",
            url=url,
            priority=2,
            adapter="betexplorer_odds",
        ),
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"<html><body>Brazil v Croatia 1.80 3.40 4.20</body></html>"
        ),
    )

    assert result.status == "ingested"
    assert result.facts[0].fact_type == "decimal_odds"
    assert result.facts[0].source_name == "betexplorer-world-cup"


def test_source_ingestion_routes_transfermarkt_squad_adapter():
    tmp_path = workspace_tmp()
    url = "https://www.transfermarkt.com/world-cup-2026/teilnehmer/pokalwettbewerb/WM26"

    result = ingest_source(
        SourceDefinition(
            category=SourceCategory.PLAYER,
            name="transfermarkt-world-cup-2026-squads",
            url=url,
            priority=3,
            adapter="transfermarkt_squads",
        ),
        snapshot_dir=tmp_path / "snapshots",
        http_client=FakeHttpClient(
            b"""
            <html><body><table>
              <tr>
                <td class="hauptlink"><a href="/neymar/profil/spieler/68290">Neymar</a></td>
                <td><img title="Brazil" /></td>
              </tr>
            </table></body></html>
            """
        ),
    )

    assert result.status == "ingested"
    assert result.facts[0].fact_type == "player_presence"
    assert result.facts[0].source_name == "transfermarkt-world-cup-2026-squads"


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
