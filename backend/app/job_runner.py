from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from app.job_repository import InMemoryJobRunRepository, JobRunRecord, JobRunRepository


JobHandler = Callable[[], dict]


@dataclass(frozen=True)
class JobDefinition:
    job_id: str
    label: str
    interval_minutes: int
    handler: JobHandler


@dataclass
class JobState:
    job_id: str
    label: str
    interval_minutes: int
    run_count: int = 0
    last_run: JobRunRecord | None = None


class InMemoryJobRunner:
    def __init__(
        self,
        definitions: list[JobDefinition],
        run_repository: JobRunRepository | None = None,
    ):
        self._definitions = {definition.job_id: definition for definition in definitions}
        self._run_repository = run_repository or InMemoryJobRunRepository()

    def list_definitions(self) -> list[JobDefinition]:
        return list(self._definitions.values())

    def list_states(self) -> list[JobState]:
        return [
            JobState(
                job_id=definition.job_id,
                label=definition.label,
                interval_minutes=definition.interval_minutes,
                run_count=self._run_repository.count_by_job(definition.job_id),
                last_run=self._run_repository.last_for_job(definition.job_id),
            )
            for definition in self._definitions.values()
        ]

    def recent_runs(self, limit: int = 20) -> list[JobRunRecord]:
        return self._run_repository.list_recent(limit=limit)

    def run(self, job_id: str) -> JobRunRecord:
        definition = self._definitions.get(job_id)
        if definition is None:
            raise KeyError(job_id)

        started_at = _now()
        try:
            summary = definition.handler()
        except Exception as error:
            record = JobRunRecord(
                id=str(uuid4()),
                job_id=job_id,
                status="failed",
                started_at=started_at,
                finished_at=_now(),
                summary={},
                error=str(error),
            )
        else:
            record = JobRunRecord(
                id=str(uuid4()),
                job_id=job_id,
                status="succeeded",
                started_at=started_at,
                finished_at=_now(),
                summary=summary,
            )

        self._run_repository.save(record)
        return record


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
