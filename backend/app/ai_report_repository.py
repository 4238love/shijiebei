from __future__ import annotations

from copy import deepcopy
import os
from typing import Protocol
from uuid import uuid4


class AIReportRepository(Protocol):
    def save(self, report: dict) -> str:
        ...

    def get(self, report_id: str) -> dict | None:
        ...


class InMemoryAIReportRepository:
    def __init__(self):
        self._reports: dict[str, dict] = {}

    def save(self, report: dict) -> str:
        report_id = report.get("id") or str(uuid4())
        saved_report = {"id": report_id, **report}
        self._reports[report_id] = deepcopy(saved_report)
        return report_id

    def get(self, report_id: str) -> dict | None:
        report = self._reports.get(report_id)
        if report is None:
            return None
        return deepcopy(report)


class PostgresAIReportRepository:
    def __init__(self, *, database_url: str, connect_factory=None):
        self.database_url = database_url
        self.connect_factory = connect_factory

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists ai_reports (
                        id text primary key,
                        payload jsonb not null,
                        created_at timestamptz not null default now()
                    )
                    """
                )

    def save(self, report: dict) -> str:
        report_id = report.get("id") or str(uuid4())
        payload = {**report, "id": report_id}

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into ai_reports (id, payload)
                    values (%s, %s)
                    on conflict (id) do update
                    set payload = excluded.payload
                    """,
                    (report_id, _json_payload(payload)),
                )

        return report_id

    def get(self, report_id: str) -> dict | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select payload from ai_reports where id = %s",
                    (report_id,),
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return dict(row[0])

    def _connect(self):
        if self.connect_factory is not None:
            return self.connect_factory()

        import psycopg

        return psycopg.connect(self.database_url)


def default_ai_report_repository() -> AIReportRepository:
    repository_kind = os.getenv("AI_REPORT_REPOSITORY", "memory")
    if repository_kind == "postgres":
        repository = PostgresAIReportRepository(database_url=os.environ["DATABASE_URL"])
        repository.ensure_schema()
        return repository

    return InMemoryAIReportRepository()


def _json_payload(payload: dict):
    try:
        from psycopg.types.json import Json
    except ModuleNotFoundError:
        return payload

    return Json(payload)
