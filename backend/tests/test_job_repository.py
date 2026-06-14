from app.job_repository import InMemoryJobRunRepository, JobRunRecord


def job_run(run_id: str, job_id: str = "validate-sources") -> JobRunRecord:
    return JobRunRecord(
        id=run_id,
        job_id=job_id,
        status="succeeded",
        started_at=f"2026-06-14T00:00:0{run_id[-1]}+00:00",
        finished_at=f"2026-06-14T00:00:1{run_id[-1]}+00:00",
        summary={"run": run_id},
    )


def test_in_memory_job_run_repository_lists_recent_runs_first():
    repository = InMemoryJobRunRepository()

    repository.save(job_run("run-1"))
    repository.save(job_run("run-2", job_id="ingest-sources"))

    recent = repository.list_recent(limit=2)

    assert [run.id for run in recent] == ["run-2", "run-1"]


def test_in_memory_job_run_repository_counts_and_finds_last_run_by_job():
    repository = InMemoryJobRunRepository()

    repository.save(job_run("run-1", job_id="validate-sources"))
    repository.save(job_run("run-2", job_id="ingest-sources"))
    repository.save(job_run("run-3", job_id="validate-sources"))

    assert repository.count_by_job("validate-sources") == 2
    assert repository.last_for_job("validate-sources").id == "run-3"
    assert repository.last_for_job("missing") is None
