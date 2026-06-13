from __future__ import annotations

from copy import deepcopy
import os
from typing import Protocol
from uuid import uuid4


class PredictionRepository(Protocol):
    def save(self, prediction: dict) -> str:
        ...

    def get(self, prediction_id: str) -> dict | None:
        ...


class InMemoryPredictionRepository:
    def __init__(self):
        self._predictions: dict[str, dict] = {}

    def save(self, prediction: dict) -> str:
        prediction_id = prediction.get("id") or str(uuid4())
        saved_prediction = {"id": prediction_id, **prediction}
        self._predictions[prediction_id] = deepcopy(saved_prediction)
        return prediction_id

    def get(self, prediction_id: str) -> dict | None:
        prediction = self._predictions.get(prediction_id)
        if prediction is None:
            return None
        return deepcopy(prediction)


class PostgresPredictionRepository:
    def __init__(self, *, database_url: str, connect_factory=None):
        self.database_url = database_url
        self.connect_factory = connect_factory

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists predictions (
                        id text primary key,
                        payload jsonb not null,
                        created_at timestamptz not null default now()
                    )
                    """
                )

    def save(self, prediction: dict) -> str:
        prediction_id = prediction.get("id") or str(uuid4())
        payload = {**prediction, "id": prediction_id}

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into predictions (id, payload)
                    values (%s, %s)
                    on conflict (id) do update
                    set payload = excluded.payload
                    """,
                    (prediction_id, _json_payload(payload)),
                )

        return prediction_id

    def get(self, prediction_id: str) -> dict | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select payload from predictions where id = %s",
                    (prediction_id,),
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


def default_prediction_repository() -> PredictionRepository:
    repository_kind = os.getenv("PREDICTION_REPOSITORY", "memory")
    if repository_kind == "postgres":
        repository = PostgresPredictionRepository(database_url=os.environ["DATABASE_URL"])
        repository.ensure_schema()
        return repository

    return InMemoryPredictionRepository()


def _json_payload(payload: dict):
    try:
        from psycopg.types.json import Json
    except ModuleNotFoundError:
        return payload

    return Json(payload)
