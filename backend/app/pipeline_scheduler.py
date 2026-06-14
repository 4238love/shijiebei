from __future__ import annotations

from dataclasses import dataclass
import os

from app.job_runner import InMemoryJobRunner


@dataclass(frozen=True)
class PipelineSchedulerStatus:
    enabled: bool
    running: bool
    job_count: int
    job_ids: list[str]


class PipelineJobScheduler:
    def __init__(
        self,
        *,
        enabled: bool,
        runner: InMemoryJobRunner,
        scheduler_factory=None,
    ):
        self.enabled = enabled
        self.runner = runner
        self.scheduler_factory = scheduler_factory
        self._scheduler = None

    def start(self) -> None:
        if not self.enabled or self._is_running():
            return

        scheduler = self._create_scheduler()
        for definition in self.runner.list_definitions():
            scheduler.add_job(
                lambda job_id=definition.job_id: self.runner.run(job_id),
                "interval",
                minutes=definition.interval_minutes,
                id=definition.job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        scheduler.start()
        self._scheduler = scheduler

    def shutdown(self) -> None:
        if not self._scheduler or not self._is_running():
            return

        self._scheduler.shutdown(wait=False)

    def status(self) -> PipelineSchedulerStatus:
        if not self.enabled or not self._scheduler:
            return PipelineSchedulerStatus(
                enabled=self.enabled,
                running=False,
                job_count=0,
                job_ids=[],
            )

        job_ids = [job.id for job in self._scheduler.get_jobs()]
        return PipelineSchedulerStatus(
            enabled=True,
            running=self._is_running(),
            job_count=len(job_ids),
            job_ids=job_ids,
        )

    def _create_scheduler(self):
        if self.scheduler_factory is not None:
            return self.scheduler_factory()

        from apscheduler.schedulers.background import BackgroundScheduler

        return BackgroundScheduler(timezone="UTC")

    def _is_running(self) -> bool:
        return bool(self._scheduler and getattr(self._scheduler, "running", False))


def create_pipeline_scheduler(
    runner: InMemoryJobRunner,
    *,
    enabled: bool | None = None,
    scheduler_factory=None,
) -> PipelineJobScheduler:
    return PipelineJobScheduler(
        enabled=_scheduler_enabled() if enabled is None else enabled,
        runner=runner,
        scheduler_factory=scheduler_factory,
    )


def _scheduler_enabled() -> bool:
    return os.getenv("ENABLE_SCHEDULER", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
