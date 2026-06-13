from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class IntervalTriggerSpec:
    minutes: int


@dataclass(frozen=True)
class JobRunResult:
    job_id: str
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class PredictionJobs:
    ingest_sources: Callable[[], None]
    create_predictions: Callable[[], None]
    collect_results: Callable[[], None]


def register_prediction_jobs(
    scheduler,
    jobs: PredictionJobs,
    *,
    ingestion_minutes: int = 30,
    prediction_minutes: int = 60,
    result_collection_minutes: int = 60,
) -> list[str]:
    schedules = [
        (
            "ingest-sources",
            lambda: run_job_safely("ingest-sources", jobs.ingest_sources),
            IntervalTriggerSpec(minutes=ingestion_minutes),
        ),
        (
            "create-predictions",
            lambda: run_job_safely("create-predictions", jobs.create_predictions),
            IntervalTriggerSpec(minutes=prediction_minutes),
        ),
        (
            "collect-results",
            lambda: run_job_safely("collect-results", jobs.collect_results),
            IntervalTriggerSpec(minutes=result_collection_minutes),
        ),
    ]

    for job_id, job, trigger in schedules:
        scheduler.add_schedule(job, trigger, id=job_id)

    return [job_id for job_id, _, _ in schedules]


def run_job_safely(job_id: str, job: Callable[[], None]) -> JobRunResult:
    try:
        job()
    except Exception as error:
        return JobRunResult(job_id=job_id, ok=False, error=str(error))

    return JobRunResult(job_id=job_id, ok=True)
