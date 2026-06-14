from app.job_runner import InMemoryJobRunner, JobDefinition
from app.pipeline_scheduler import PipelineJobScheduler


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


def runner_with_calls(calls: list[str]) -> InMemoryJobRunner:
    return InMemoryJobRunner(
        [
            JobDefinition(
                job_id="ingest-sources",
                label="Ingest configured sources",
                interval_minutes=30,
                handler=lambda: calls.append("ingest-sources") or {},
            ),
            JobDefinition(
                job_id="validate-sources",
                label="Validate source facts",
                interval_minutes=45,
                handler=lambda: calls.append("validate-sources") or {},
            ),
        ]
    )


def test_pipeline_scheduler_starts_interval_jobs_for_runner_definitions():
    calls = []
    fake_scheduler = FakeBackgroundScheduler()
    scheduler = PipelineJobScheduler(
        enabled=True,
        runner=runner_with_calls(calls),
        scheduler_factory=lambda: fake_scheduler,
    )

    scheduler.start()

    assert fake_scheduler.running is True
    assert [job["id"] for job in fake_scheduler.jobs] == [
        "ingest-sources",
        "validate-sources",
    ]
    assert [job["minutes"] for job in fake_scheduler.jobs] == [30, 45]

    fake_scheduler.jobs[0]["func"]()

    assert calls == ["ingest-sources"]
    assert scheduler.status().job_ids == ["ingest-sources", "validate-sources"]


def test_pipeline_scheduler_is_noop_when_disabled():
    fake_scheduler = FakeBackgroundScheduler()
    scheduler = PipelineJobScheduler(
        enabled=False,
        runner=runner_with_calls([]),
        scheduler_factory=lambda: fake_scheduler,
    )

    scheduler.start()

    status = scheduler.status()
    assert fake_scheduler.running is False
    assert status.enabled is False
    assert status.running is False
    assert status.job_count == 0


def test_pipeline_scheduler_shutdown_stops_running_scheduler():
    fake_scheduler = FakeBackgroundScheduler()
    scheduler = PipelineJobScheduler(
        enabled=True,
        runner=runner_with_calls([]),
        scheduler_factory=lambda: fake_scheduler,
    )

    scheduler.start()
    scheduler.shutdown()

    assert fake_scheduler.running is False
    assert fake_scheduler.shutdown_wait is False
