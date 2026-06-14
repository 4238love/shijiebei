from __future__ import annotations

from copy import deepcopy
import os
from typing import Protocol
from uuid import uuid4


class BacktestRepository(Protocol):
    def save(self, backtest_run: dict) -> str:
        ...

    def get(self, backtest_id: str) -> dict | None:
        ...


class InMemoryBacktestRepository:
    def __init__(self):
        self._backtest_runs: dict[str, dict] = {}

    def save(self, backtest_run: dict) -> str:
        backtest_id = backtest_run.get("id") or str(uuid4())
        saved_run = {"id": backtest_id, **backtest_run}
        self._backtest_runs[backtest_id] = deepcopy(saved_run)
        return backtest_id

    def get(self, backtest_id: str) -> dict | None:
        backtest_run = self._backtest_runs.get(backtest_id)
        if backtest_run is None:
            return None
        return deepcopy(backtest_run)


class PostgresBacktestRepository:
    def __init__(self, *, database_url: str, connect_factory=None):
        self.database_url = database_url
        self.connect_factory = connect_factory

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists backtest_runs (
                        id text primary key,
                        payload jsonb not null,
                        created_at timestamptz not null default now()
                    )
                    """
                )

    def save(self, backtest_run: dict) -> str:
        backtest_id = backtest_run.get("id") or str(uuid4())
        payload = {**backtest_run, "id": backtest_id}

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into backtest_runs (id, payload)
                    values (%s, %s)
                    on conflict (id) do update
                    set payload = excluded.payload
                    """,
                    (backtest_id, _json_payload(payload)),
                )

        return backtest_id

    def get(self, backtest_id: str) -> dict | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select payload from backtest_runs where id = %s",
                    (backtest_id,),
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


def default_backtest_repository() -> BacktestRepository:
    repository_kind = os.getenv("BACKTEST_REPOSITORY", "memory")
    if repository_kind == "postgres":
        repository = PostgresBacktestRepository(database_url=os.environ["DATABASE_URL"])
        repository.ensure_schema()
        return repository

    return InMemoryBacktestRepository()


def _json_payload(payload: dict):
    try:
        from psycopg.types.json import Json
    except ModuleNotFoundError:
        return payload

    return Json(payload)
