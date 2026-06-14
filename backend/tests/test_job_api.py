from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.job_repository import InMemoryJobRunRepository, JobRunRecord
from app.main import create_app


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


def workspace_tmp() -> Path:
    path = Path(".test-output") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def configured_app(
    *,
    job_run_repository=None,
    enable_scheduler=None,
    scheduler_factory=None,
):
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
    return create_app(
        source_config_path=config_path,
        source_snapshot_dir=tmp_path / "snapshots",
        source_http_client=UrlMappedHttpClient(
            {
                ranking_url: b"<html><body>1 Brazil 2082 12 Croatia 1900</body></html>",
            }
        ),
        job_run_repository=job_run_repository,
        enable_scheduler=enable_scheduler,
        scheduler_factory=scheduler_factory,
    )


def configured_client(**kwargs) -> TestClient:
    return TestClient(configured_app(**kwargs))


class FakeScheduledJob:
    def __init__(self, job_id: str):
        self.id = job_id


class FakeBackgroundScheduler:
    def __init__(self):
        self.jobs = []
        self.running = False
        self.shutdown_wait = None

    def add_job(self, func, trigger, *, minutes, id, replace_existing, max_instances, coalesce):
        self.jobs.append(
            {
                "func": func,
                "trigger": trigger,
                "minutes": minutes,
                "id": id,
                "replace_existing": replace_existing,
                "max_instances": max_instances,
                "coalesce": coalesce,
            }
        )

    def start(self):
        self.running = True

    def shutdown(self, *, wait):
        self.running = False
        self.shutdown_wait = wait

    def get_jobs(self):
        return [FakeScheduledJob(job["id"]) for job in self.jobs]


def test_jobs_endpoint_lists_registered_pipeline_jobs():
    response = configured_client().get("/jobs")

    assert response.status_code == 200
    body = response.json()
    assert [job["job_id"] for job in body["jobs"]] == [
        "ingest-sources",
        "validate-sources",
        "create-source-backed-prediction",
        "predict-tomorrow-world-cup-matches",
    ]
    assert body["scheduler"] == {
        "enabled": False,
        "running": False,
        "job_count": 0,
        "job_ids": [],
    }
    assert body["recent_runs"] == []


def test_validate_sources_job_records_status_and_summary():
    client = configured_client()

    run_response = client.post("/jobs/validate-sources/run")

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["status"] == "succeeded"
    assert run["summary"]["source_count"] == 1
    assert run["summary"]["validated_fact_count"] == 4

    jobs_response = client.get("/jobs")
    job = next(
        item
        for item in jobs_response.json()["jobs"]
        if item["job_id"] == "validate-sources"
    )
    assert job["run_count"] == 1
    assert job["last_run"]["id"] == run["id"]


def test_jobs_endpoint_reads_existing_run_repository_state():
    repository = InMemoryJobRunRepository()
    repository.save(
        JobRunRecord(
            id="existing-run",
            job_id="validate-sources",
            status="succeeded",
            started_at="2026-06-14T00:00:00+00:00",
            finished_at="2026-06-14T00:00:01+00:00",
            summary={"source_count": 1},
        )
    )
    client = configured_client(job_run_repository=repository)

    response = client.get("/jobs")

    assert response.status_code == 200
    body = response.json()
    job = next(item for item in body["jobs"] if item["job_id"] == "validate-sources")
    assert job["run_count"] == 1
    assert job["last_run"]["id"] == "existing-run"
    assert body["recent_runs"][0]["id"] == "existing-run"


def test_jobs_endpoint_reports_running_scheduler_when_enabled():
    fake_scheduler = FakeBackgroundScheduler()
    app = configured_app(
        enable_scheduler=True,
        scheduler_factory=lambda: fake_scheduler,
    )

    with TestClient(app) as client:
        response = client.get("/jobs")

    assert response.status_code == 200
    scheduler = response.json()["scheduler"]
    assert scheduler["enabled"] is True
    assert scheduler["running"] is True
    assert scheduler["job_count"] == 4
    assert scheduler["job_ids"] == [
        "ingest-sources",
        "validate-sources",
        "create-source-backed-prediction",
        "predict-tomorrow-world-cup-matches",
    ]
    assert fake_scheduler.shutdown_wait is False


def test_prediction_job_creates_saved_prediction_record():
    client = configured_client()

    run_response = client.post("/jobs/create-source-backed-prediction/run")

    assert run_response.status_code == 200
    run = run_response.json()
    prediction_id = run["summary"]["prediction_id"]
    assert run["status"] == "succeeded"
    assert run["summary"]["source_category"] == "ranking"

    detail_response = client.get(f"/predictions/{prediction_id}/record")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["prediction"]["id"] == prediction_id
    assert detail["source_summary"]["ingested_source_count"] == 1
    assert detail["source_evidence"][0]["source_name"] == "ranking-source"
    assert detail["validated_facts"]
    assert detail["validated_facts"][0]["fact_type"] == "team_ranking_position"


def test_tomorrow_world_cup_job_predicts_all_target_date_matches(monkeypatch):
    monkeypatch.setenv("JOB_TARGET_DATE", "2026-06-15")
    monkeypatch.setenv("JOB_SIMULATION_COUNT", "250")

    tmp_path = workspace_tmp()
    config_path = tmp_path / "sources.json"
    schedule_url = "https://data-source.example/schedule.html"
    ranking_url = "https://data-source.example/ranking.html"
    config_path.write_text(
        """
        {
          "schedule": [
            {
              "name": "fixture-source",
              "url": "https://data-source.example/schedule.html",
              "priority": 1,
              "adapter": "schema_org_schedule"
            }
          ],
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
    app = create_app(
        source_config_path=config_path,
        source_snapshot_dir=tmp_path / "snapshots",
        source_http_client=UrlMappedHttpClient(
            {
                schedule_url: b"""
                <html><script type="application/ld+json">
                {"@graph":[
                  {"@type":"SportsEvent","sport":"Football","name":"Brazil - Morocco","startDate":"2026-06-15T19:00:00+00:00"},
                  {"@type":"SportsEvent","sport":"Football","name":"Germany vs Curacao","startDate":"2026-06-15T22:00:00+00:00"},
                  {"@type":"SportsEvent","sport":"Football","name":"Argentina vs France","startDate":"2026-06-16T19:00:00+00:00"}
                ]}
                </script></html>
                """,
                ranking_url: (
                    b"<html><body>"
                    b"1 Brazil 2082 10 Germany 1920 "
                    b"14 Morocco 1800 88 Curacao 1300 "
                    b"2 Argentina 2050 3 France 2025"
                    b"</body></html>"
                ),
            }
        ),
    )
    client = TestClient(app)

    run_response = client.post("/jobs/predict-tomorrow-world-cup-matches/run")

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["status"] == "succeeded"
    assert run["summary"]["target_date"] == "2026-06-15"
    assert run["summary"]["match_count"] == 2
    assert run["summary"]["prediction_count"] == 2
    assert [
        (prediction["home_team"], prediction["away_team"])
        for prediction in run["summary"]["predictions"]
    ] == [("Brazil", "Morocco"), ("Germany", "Curacao")]

    first_prediction = run["summary"]["predictions"][0]
    assert first_prediction["predicted_winner"] in {"Brazil", "Morocco", "Draw"}
    assert first_prediction["predicted_scoreline"].count("-") == 1
    assert first_prediction["prediction_id"]

    detail_response = client.get(
        f"/predictions/{first_prediction['prediction_id']}/record"
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["prediction"]["home_team"] == "Brazil"
    assert detail["prediction"]["away_team"] == "Morocco"
    assert detail["source_summary"]["ingested_source_count"] == 2


def test_running_unknown_job_returns_404():
    response = configured_client().post("/jobs/missing/run")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"
