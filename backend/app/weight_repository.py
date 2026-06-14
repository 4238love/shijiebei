from __future__ import annotations

from copy import deepcopy
import os

from app.prediction_engine import WeightVersion
from app.weights import WeightRecommendation, WeightRecommendationStatus


class InMemoryWeightRepository:
    def __init__(self):
        self._recommendations: dict[str, WeightRecommendation] = {}
        self._active_weight_version: WeightVersion | None = None

    def save_recommendation(self, recommendation: WeightRecommendation) -> None:
        self._recommendations[recommendation.id] = deepcopy(recommendation)

    def get_recommendation(
        self, recommendation_id: str
    ) -> WeightRecommendation | None:
        recommendation = self._recommendations.get(recommendation_id)
        if recommendation is None:
            return None
        return deepcopy(recommendation)

    def save_active_weight_version(self, weight_version: WeightVersion) -> None:
        self._active_weight_version = deepcopy(weight_version)

    def get_active_weight_version(self) -> WeightVersion | None:
        if self._active_weight_version is None:
            return None
        return deepcopy(self._active_weight_version)


class PostgresWeightRepository:
    def __init__(self, *, database_url: str, connect_factory=None):
        self.database_url = database_url
        self.connect_factory = connect_factory

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists weight_recommendations (
                        id text primary key,
                        payload jsonb not null,
                        created_at timestamptz not null default now()
                    )
                    """
                )
                cursor.execute(
                    """
                    create table if not exists weight_versions (
                        name text primary key,
                        payload jsonb not null,
                        is_active boolean not null default false,
                        created_at timestamptz not null default now()
                    )
                    """
                )

    def save_recommendation(self, recommendation: WeightRecommendation) -> None:
        payload = _recommendation_payload(recommendation)

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into weight_recommendations (id, payload)
                    values (%s, %s)
                    on conflict (id) do update
                    set payload = excluded.payload
                    """,
                    (recommendation.id, _json_payload(payload)),
                )

    def get_recommendation(
        self, recommendation_id: str
    ) -> WeightRecommendation | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select payload from weight_recommendations where id = %s",
                    (recommendation_id,),
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return _recommendation_from_payload(dict(row[0]))

    def save_active_weight_version(self, weight_version: WeightVersion) -> None:
        payload = _weight_version_payload(weight_version)

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("update weight_versions set is_active = false")
                cursor.execute(
                    """
                    insert into weight_versions (name, payload, is_active)
                    values (%s, %s, true)
                    on conflict (name) do update
                    set payload = excluded.payload,
                        is_active = true
                    """,
                    (weight_version.name, _json_payload(payload)),
                )

    def get_active_weight_version(self) -> WeightVersion | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select payload from weight_versions
                    where is_active = true
                    order by created_at desc
                    limit 1
                    """
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return _weight_version_from_payload(dict(row[0]))

    def _connect(self):
        if self.connect_factory is not None:
            return self.connect_factory()

        import psycopg

        return psycopg.connect(self.database_url)


def default_weight_repository():
    repository_kind = os.getenv("WEIGHT_REPOSITORY", "memory")
    if repository_kind == "postgres":
        repository = PostgresWeightRepository(database_url=os.environ["DATABASE_URL"])
        repository.ensure_schema()
        return repository

    return InMemoryWeightRepository()


def _recommendation_payload(recommendation: WeightRecommendation) -> dict:
    return {
        "id": recommendation.id,
        "provider_name": recommendation.provider_name,
        "proposed_factors": recommendation.proposed_factors,
        "rationale": recommendation.rationale,
        "status": recommendation.status.value,
        "reviewer": recommendation.reviewer,
        "backtest_reference": recommendation.backtest_reference,
        "activated_version_name": recommendation.activated_version_name,
    }


def _recommendation_from_payload(payload: dict) -> WeightRecommendation:
    return WeightRecommendation(
        id=payload["id"],
        provider_name=payload["provider_name"],
        proposed_factors=dict(payload["proposed_factors"]),
        rationale=payload["rationale"],
        status=WeightRecommendationStatus(payload["status"]),
        reviewer=payload.get("reviewer"),
        backtest_reference=payload.get("backtest_reference"),
        activated_version_name=payload.get("activated_version_name"),
    )


def _weight_version_payload(weight_version: WeightVersion) -> dict:
    return {
        "name": weight_version.name,
        "factors": weight_version.factors,
    }


def _weight_version_from_payload(payload: dict) -> WeightVersion:
    return WeightVersion(
        name=payload["name"],
        factors=dict(payload["factors"]),
    )


def _json_payload(payload: dict):
    try:
        from psycopg.types.json import Json
    except ModuleNotFoundError:
        return payload

    return Json(payload)
