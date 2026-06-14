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
