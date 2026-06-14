from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import os
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class JobRunRecord:
    id: str
    job_id: str
    status: str
    started_at: str
    finished_at: str
    summary: dict
    error: str | None = None


class JobRunRepository(Protocol):
    def save(self, record: JobRunRecord) -> str:
        ...

    def list_recent(self, limit: int = 20) -> list[JobRunRecord]:
        ...

    def count_by_job(self, job_id: str) -> int:
        ...

    def last_for_job(self, job_id: str) -> JobRunRecord | None:
        ...


class InMemoryJobRunRepository:
    def __init__(self):
        self._records: dict[str, JobRunRecord] = {}
        self._record_ids: list[str] = []

    def save(self, record: JobRunRecord) -> str:
        record_id = record.id or str(uuid4())
        saved_record = JobRunRecord(
            id=record_id,
            job_id=record.job_id,
            status=record.status,
            started_at=record.started_at,
            finished_at=record.finished_at,
            summary=deepcopy(record.summary),
            error=record.error,
        )
        self._records[record_id] = saved_record
        if record_id in self._record_ids:
            self._record_ids.remove(record_id)
        self._record_ids.append(record_id)
        return record_id

    def list_recent(self, limit: int = 20) -> list[JobRunRecord]:
        return [
            deepcopy(self._records[record_id])
            for record_id in reversed(self._record_ids[-limit:])
        ]

    def count_by_job(self, job_id: str) -> int:
        return sum(1 for record in self._records.values() if record.job_id == job_id)

    def last_for_job(self, job_id: str) -> JobRunRecord | None:
        for record_id in reversed(self._record_ids):
            record = self._records[record_id]
            if record.job_id == job_id:
                return deepcopy(record)
        return None


class PostgresJobRunRepository:
    def __init__(self, *, database_url: str, connect_factory=None):
        self.database_url = database_url
        self.connect_factory = connect_factory

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists job_runs (
                        id text primary key,
                        job_id text not null,
                        status text not null,
                        started_at timestamptz not null,
                        finished_at timestamptz not null,
                        payload jsonb not null,
                        created_at timestamptz not null default now()
                    )
                    """
                )
                cursor.execute(
                    """
                    create index if not exists job_runs_job_id_started_at_idx
                    on job_runs (job_id, started_at desc)
                    """
                )
                cursor.execute(
                    """
                    create index if not exists job_runs_started_at_idx
                    on job_runs (started_at desc)
                    """
                )

    def save(self, record: JobRunRecord) -> str:
        record_id = record.id or str(uuid4())
        saved_record = JobRunRecord(
            id=record_id,
            job_id=record.job_id,
            status=record.status,
            started_at=record.started_at,
            finished_at=record.finished_at,
            summary=deepcopy(record.summary),
            error=record.error,
        )
        payload = _record_payload(saved_record)

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into job_runs (
                        id,
                        job_id,
                        status,
                        started_at,
                        finished_at,
                        payload
                    )
                    values (%s, %s, %s, %s, %s, %s)
                    on conflict (id) do update
                    set
                        job_id = excluded.job_id,
                        status = excluded.status,
                        started_at = excluded.started_at,
                        finished_at = excluded.finished_at,
                        payload = excluded.payload
                    """,
                    (
                        record_id,
                        saved_record.job_id,
                        saved_record.status,
                        saved_record.started_at,
                        saved_record.finished_at,
                        _json_payload(payload),
                    ),
                )

        return record_id

    def list_recent(self, limit: int = 20) -> list[JobRunRecord]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select payload
                    from job_runs
                    order by started_at desc
                    limit %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()

        return [_record_from_payload(dict(row[0])) for row in rows]

    def count_by_job(self, job_id: str) -> int:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select count(*) from job_runs where job_id = %s",
                    (job_id,),
                )
                row = cursor.fetchone()

        return int(row[0]) if row else 0

    def last_for_job(self, job_id: str) -> JobRunRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select payload
                    from job_runs
                    where job_id = %s
                    order by started_at desc
                    limit 1
                    """,
                    (job_id,),
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return _record_from_payload(dict(row[0]))

    def _connect(self):
        if self.connect_factory is not None:
            return self.connect_factory()

        import psycopg

        return psycopg.connect(self.database_url)


def default_job_run_repository() -> JobRunRepository:
    repository_kind = os.getenv("JOB_RUN_REPOSITORY", "memory")
    if repository_kind == "postgres":
        repository = PostgresJobRunRepository(database_url=os.environ["DATABASE_URL"])
        repository.ensure_schema()
        return repository

    return InMemoryJobRunRepository()


def _record_payload(record: JobRunRecord) -> dict:
    return {
        "id": record.id,
        "job_id": record.job_id,
        "status": record.status,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "summary": record.summary,
        "error": record.error,
    }


def _record_from_payload(payload: dict) -> JobRunRecord:
    return JobRunRecord(
        id=payload["id"],
        job_id=payload["job_id"],
        status=payload["status"],
        started_at=payload["started_at"],
        finished_at=payload["finished_at"],
        summary=dict(payload.get("summary", {})),
        error=payload.get("error"),
    )


def _json_payload(payload: dict):
    try:
        from psycopg.types.json import Json
    except ModuleNotFoundError:
        return payload

    return Json(payload)
