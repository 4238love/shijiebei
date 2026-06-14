from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4


JobHandler = Callable[[], dict]


@dataclass(frozen=True)
class JobDefinition:
    job_id: str
    label: str
    interval_minutes: int
    handler: JobHandler


@dataclass(frozen=True)
class JobRunRecord:
    id: str
    job_id: str
    status: str
    started_at: str
    finished_at: str
    summary: dict
    error: str | None = None


@dataclass
class JobState:
    job_id: str
    label: str
    interval_minutes: int
    run_count: int = 0
    last_run: JobRunRecord | None = None


class InMemoryJobRunner:
    def __init__(self, definitions: list[JobDefinition]):
        self._definitions = {definition.job_id: definition for definition in definitions}
        self._states = {
            definition.job_id: JobState(
                job_id=definition.job_id,
                label=definition.label,
                interval_minutes=definition.interval_minutes,
            )
            for definition in definitions
        }
        self._runs: list[JobRunRecord] = []

    def list_states(self) -> list[JobState]:
        return list(self._states.values())

    def recent_runs(self, limit: int = 20) -> list[JobRunRecord]:
        return list(reversed(self._runs[-limit:]))

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

        self._runs.append(record)
        state = self._states[job_id]
        state.run_count += 1
        state.last_run = record
        return record


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
