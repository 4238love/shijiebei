from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def workspace_tmp() -> Path:
    path = Path(".test-output") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class UrlMappedHttpClient:
    def __init__(self, content_by_url: dict[str, bytes]):
        self.content_by_url = content_by_url

    def get(self, url, timeout, headers=None, follow_redirects=False):
        return FakeResponse(self.content_by_url[url])


def prediction_request() -> dict:
    return {
        "dataset": {
            "home_team": "Brazil",
            "away_team": "Croatia",
            "home": {"attack_index": 1.35, "defense_weakness": 0.82},
            "away": {"attack_index": 0.96, "defense_weakness": 1.05},
            "home_advantage": 1.08,
            "conflict_count": 0,
        },
        "weight_version": {
            "name": "baseline",
            "factors": {},
        },
        "simulation_count": 2_000,
        "seed": 20260613,
    }


def test_create_and_retrieve_match_prediction():
    client = TestClient(create_app())

    created = client.post("/predictions", json=prediction_request())

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["id"]
    assert created_body["home_team"] == "Brazil"
    assert created_body["away_team"] == "Croatia"
    assert set(created_body["probabilities"]) == {"home_win", "draw", "away_win"}
    assert len(created_body["top_scorelines"]) == 5

    retrieved = client.get(f"/predictions/{created_body['id']}")

    assert retrieved.status_code == 200
    assert retrieved.json() == created_body


def test_list_predictions_returns_recent_saved_predictions():
    client = TestClient(create_app())
    first = client.post("/predictions", json=prediction_request()).json()
    second_payload = prediction_request()
    second_payload["dataset"]["home_team"] = "Argentina"
    second_payload["dataset"]["away_team"] = "France"
    second = client.post("/predictions", json=second_payload).json()

    response = client.get("/predictions")

    assert response.status_code == 200
    body = response.json()
    assert [prediction["id"] for prediction in body["predictions"]] == [
        second["id"],
        first["id"],
    ]
    assert body["predictions"][0]["home_team"] == "Argentina"


def test_retrieving_unknown_prediction_returns_404():
    client = TestClient(create_app())

    response = client.get("/predictions/not-found")

    assert response.status_code == 404
    assert response.json()["detail"] == "Match prediction not found"


def test_create_match_prediction_from_sources():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    ranking_url = "https://data-source.example/ranking.html"
    form_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
    config_path.write_text(
        """
        {
          "ranking": [
            {
              "name": "ranking-source",
              "url": "https://data-source.example/ranking.html",
              "priority": 1,
              "adapter": "webpage"
            }
          ],
          "team_form": [
            {
              "name": "form-source",
              "url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
              "priority": 1,
              "adapter": "espn_scoreboard"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=UrlMappedHttpClient(
                {
                    ranking_url: b"<html><body>1 Brazil 2082 12 Croatia 1900</body></html>",
                    form_url: b"""
                    {
                      "events": [
                        {
                          "id": "401752999",
                          "date": "2026-06-20T19:00Z",
                          "status": {"type": {"description": "Final"}},
                          "competitions": [
                            {
                              "competitors": [
                                {
                                  "homeAway": "home",
                                  "team": {"displayName": "Brazil"},
                                  "score": "2"
                                },
                                {
                                  "homeAway": "away",
                                  "team": {"displayName": "Croatia"},
                                  "score": "1"
                                }
                              ]
                            }
                          ]
                        }
                      ]
                    }
                    """,
                }
            ),
        )
    )

    response = client.post(
        "/predictions/from-sources",
        json={
            "home_team": "Brazil",
            "away_team": "Croatia",
            "home_advantage": 1.08,
            "simulation_count": 1_000,
            "seed": 20260614,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["prediction"]["id"]
    assert body["prediction"]["home_team"] == "Brazil"
    assert body["prediction"]["away_team"] == "Croatia"
    assert body["dataset"]["home"]["attack_index"] > body["dataset"]["away"][
        "attack_index"
    ]
    assert body["source_summary"]["ingested_source_count"] == 2
    assert body["source_summary"]["validated_fact_count"] > 0
    assert body["validated_facts"]
    assert body["validated_facts"][0]["fact_type"]
    assert len(body["source_evidence"]) == 2
    assert body["source_evidence"][0]["snapshot_path"]

    detail_response = client.get(f"/predictions/{body['prediction']['id']}/record")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["prediction"] == body["prediction"]
    assert detail["dataset"] == body["dataset"]
    assert detail["source_summary"] == body["source_summary"]
    assert detail["source_evidence"] == body["source_evidence"]
    assert detail["validated_facts"] == body["validated_facts"]


def test_create_match_prediction_from_sources_can_generate_ai_report():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    ranking_url = "https://data-source.example/ranking.html"
    config_path.write_text(
        """
        {
          "ranking": [
            {
              "name": "ranking-source",
              "url": "https://data-source.example/ranking.html",
              "priority": 1,
              "adapter": "webpage"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=UrlMappedHttpClient(
                {
                    ranking_url: b"<html><body>1 Brazil 2082 12 Croatia 1900</body></html>",
                }
            ),
        )
    )

    response = client.post(
        "/predictions/from-sources",
        json={
            "home_team": "Brazil",
            "away_team": "Croatia",
            "category": "ranking",
            "simulation_count": 1_000,
            "seed": 20260614,
            "generate_ai_report": True,
            "ai_report_provider": "gpt",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ai_report"]["id"]
    assert body["ai_report"]["provider_name"] == "gpt"
    assert "Brazil vs Croatia" in body["ai_report"]["content"]
    assert (
        body["ai_report"]["input_summary"]["probabilities"]
        == body["prediction"]["probabilities"]
    )

    detail_response = client.get(f"/predictions/{body['prediction']['id']}/record")
    standalone_report_response = client.get(f"/ai-reports/{body['ai_report']['id']}")

    assert detail_response.status_code == 200
    assert detail_response.json()["ai_report"] == body["ai_report"]
    assert standalone_report_response.status_code == 200
    assert standalone_report_response.json() == body["ai_report"]


def test_create_match_prediction_from_odds_sources_uses_market_prices():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    odds_url = "https://data-source.example/odds.html"
    config_path.write_text(
        """
        {
          "odds": [
            {
              "name": "odds-source",
              "url": "https://data-source.example/odds.html",
              "priority": 1,
              "adapter": "webpage"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=UrlMappedHttpClient(
                {
                    odds_url: b"<html><body>Brazil v Croatia 1.80 3.40 4.20</body></html>",
                }
            ),
        )
    )

    response = client.post(
        "/predictions/from-sources",
        json={
            "home_team": "Brazil",
            "away_team": "Croatia",
            "category": "odds",
            "simulation_count": 1_000,
            "seed": 20260614,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source_summary"]["validated_fact_count"] == 3
    assert body["dataset"]["home"]["attack_index"] > body["dataset"]["away"][
        "attack_index"
    ]
    assert body["dataset"]["home"]["defense_weakness"] < body["dataset"]["away"][
        "defense_weakness"
    ]


def test_create_match_prediction_from_betexplorer_odds_row_uses_market_prices():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    odds_url = "https://data-source.example/betexplorer.html"
    config_path.write_text(
        """
        {
          "odds": [
            {
              "name": "betexplorer-source",
              "url": "https://data-source.example/betexplorer.html",
              "priority": 1,
              "adapter": "webpage"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=UrlMappedHttpClient(
                {
                    odds_url: b"""
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
                    """,
                }
            ),
        )
    )

    response = client.post(
        "/predictions/from-sources",
        json={
            "home_team": "Brazil",
            "away_team": "Morocco",
            "category": "odds",
            "simulation_count": 1_000,
            "seed": 20260614,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source_summary"]["validated_fact_count"] == 3
    assert body["dataset"]["home"]["attack_index"] > body["dataset"]["away"][
        "attack_index"
    ]
    assert body["dataset"]["home"]["defense_weakness"] < body["dataset"]["away"][
        "defense_weakness"
    ]


def test_create_match_prediction_from_injury_sources_uses_team_availability():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    injury_url = "https://data-source.example/injuries.html"
    config_path.write_text(
        """
        {
          "injury": [
            {
              "name": "injury-source",
              "url": "https://data-source.example/injuries.html",
              "priority": 1,
              "adapter": "webpage"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=UrlMappedHttpClient(
                {
                    injury_url: b"<html><body>Brazil: Neymar doubtful, Vinicius Junior suspended. Croatia: Modric available.</body></html>",
                }
            ),
        )
    )

    response = client.post(
        "/predictions/from-sources",
        json={
            "home_team": "Brazil",
            "away_team": "Croatia",
            "category": "injury",
            "simulation_count": 1_000,
            "seed": 20260614,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source_summary"]["validated_fact_count"] == 5
    assert body["dataset"]["home"]["attack_index"] < body["dataset"]["away"][
        "attack_index"
    ]
    assert body["dataset"]["home"]["defense_weakness"] > body["dataset"]["away"][
        "defense_weakness"
    ]


def test_create_match_prediction_from_player_sources_uses_squad_depth():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    brazil_url = "https://data-source.example/brazil-squad.html"
    croatia_url = "https://data-source.example/croatia-squad.html"
    config_path.write_text(
        """
        {
          "player": [
            {
              "name": "brazil-squad-source",
              "url": "https://data-source.example/brazil-squad.html",
              "priority": 1,
              "adapter": "webpage"
            },
            {
              "name": "croatia-squad-source",
              "url": "https://data-source.example/croatia-squad.html",
              "priority": 1,
              "adapter": "webpage"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=UrlMappedHttpClient(
                {
                    brazil_url: b"<html><body>Brazil squad: Neymar, Vinicius Junior, Alisson</body></html>",
                    croatia_url: b"<html><body>Croatia squad: Modric</body></html>",
                }
            ),
        )
    )

    response = client.post(
        "/predictions/from-sources",
        json={
            "home_team": "Brazil",
            "away_team": "Croatia",
            "category": "player",
            "simulation_count": 1_000,
            "seed": 20260614,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source_summary"]["validated_fact_count"] == 6
    assert body["dataset"]["home"]["attack_index"] > body["dataset"]["away"][
        "attack_index"
    ]
    assert body["dataset"]["home"]["defense_weakness"] < body["dataset"]["away"][
        "defense_weakness"
    ]


def test_create_match_prediction_from_news_sources_uses_team_sentiment():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    news_url = "https://data-source.example/news.html"
    config_path.write_text(
        """
        {
          "news_sentiment": [
            {
              "name": "news-source",
              "url": "https://data-source.example/news.html",
              "priority": 1,
              "adapter": "webpage"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=UrlMappedHttpClient(
                {
                    news_url: b"<html><body>Brazil: confident boost. Croatia: injury concern pressure.</body></html>",
                }
            ),
        )
    )

    response = client.post(
        "/predictions/from-sources",
        json={
            "home_team": "Brazil",
            "away_team": "Croatia",
            "category": "news_sentiment",
            "simulation_count": 1_000,
            "seed": 20260614,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source_summary"]["validated_fact_count"] == 3
    assert body["dataset"]["home"]["attack_index"] > body["dataset"]["away"][
        "attack_index"
    ]
    assert body["dataset"]["home"]["defense_weakness"] < body["dataset"]["away"][
        "defense_weakness"
    ]


def test_list_predictions_includes_source_summary_for_source_backed_runs():
    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    ranking_url = "https://data-source.example/ranking.html"
    config_path.write_text(
        """
        {
          "ranking": [
            {
              "name": "ranking-source",
              "url": "https://data-source.example/ranking.html",
              "priority": 1,
              "adapter": "webpage"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    client = TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=UrlMappedHttpClient(
                {
                    ranking_url: b"<html><body>1 Brazil 2082 12 Croatia 1900</body></html>",
                }
            ),
        )
    )
    client.post(
        "/predictions/from-sources",
        json={
            "home_team": "Brazil",
            "away_team": "Croatia",
            "category": "ranking",
            "simulation_count": 1_000,
            "seed": 20260614,
        },
    )

    response = client.get("/predictions")

    assert response.status_code == 200
    item = response.json()["predictions"][0]
    assert item["source_summary"]["ingested_source_count"] == 1
