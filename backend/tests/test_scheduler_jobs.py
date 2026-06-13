from app.scheduler_jobs import PredictionJobs, register_prediction_jobs, run_job_safely


class FakeScheduler:
    def __init__(self):
        self.schedules = []

    def add_schedule(self, func, trigger, *, id):
        self.schedules.append({"id": id, "func": func, "trigger": trigger})


def test_registers_ingestion_prediction_and_result_collection_jobs():
    scheduler = FakeScheduler()
    jobs = PredictionJobs(
        ingest_sources=lambda: None,
        create_predictions=lambda: None,
        collect_results=lambda: None,
    )

    registered = register_prediction_jobs(scheduler, jobs)

    assert registered == ["ingest-sources", "create-predictions", "collect-results"]
    assert [schedule["id"] for schedule in scheduler.schedules] == registered
    assert all(schedule["trigger"].minutes > 0 for schedule in scheduler.schedules)


def test_scheduled_job_failures_are_captured_without_raising():
    def broken_job():
        raise RuntimeError("source failed")

    result = run_job_safely("ingest-sources", broken_job)

    assert result.job_id == "ingest-sources"
    assert result.ok is False
    assert result.error == "source failed"


def test_successful_scheduled_job_reports_ok():
    calls = []

    result = run_job_safely("create-predictions", lambda: calls.append("ran"))

    assert result.ok is True
    assert result.error is None
    assert calls == ["ran"]
