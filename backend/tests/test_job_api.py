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


def configured_client(job_run_repository=None) -> TestClient:
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
    return TestClient(
        create_app(
            source_config_path=config_path,
            source_snapshot_dir=tmp_path / "snapshots",
            source_http_client=UrlMappedHttpClient(
                {
                    ranking_url: b"<html><body>1 Brazil 2082 12 Croatia 1900</body></html>",
                }
            ),
            job_run_repository=job_run_repository,
        )
    )


def test_jobs_endpoint_lists_registered_pipeline_jobs():
    response = configured_client().get("/jobs")

    assert response.status_code == 200
    body = response.json()
    assert [job["job_id"] for job in body["jobs"]] == [
        "ingest-sources",
        "validate-sources",
        "create-source-backed-prediction",
    ]
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


def test_running_unknown_job_returns_404():
    response = configured_client().post("/jobs/missing/run")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"
