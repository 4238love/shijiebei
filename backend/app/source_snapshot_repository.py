from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import os
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class SourceSnapshotMetadata:
    id: str
    source_name: str
    category: str | None
    status: str
    path: str
    content_hash: str
    item_count: int
    fact_count: int
    match_count: int
    message: str | None


class SourceSnapshotRepository(Protocol):
    def save(self, snapshot: SourceSnapshotMetadata) -> str:
        ...

    def list_recent(self, *, limit: int = 50) -> list[SourceSnapshotMetadata]:
        ...


class InMemorySourceSnapshotRepository:
    def __init__(self):
        self._snapshots: dict[str, SourceSnapshotMetadata] = {}
        self._snapshot_ids: list[str] = []

    def save(self, snapshot: SourceSnapshotMetadata) -> str:
        snapshot_id = snapshot.id or str(uuid4())
        saved_snapshot = SourceSnapshotMetadata(
            id=snapshot_id,
            source_name=snapshot.source_name,
            category=snapshot.category,
            status=snapshot.status,
            path=snapshot.path,
            content_hash=snapshot.content_hash,
            item_count=snapshot.item_count,
            fact_count=snapshot.fact_count,
            match_count=snapshot.match_count,
            message=snapshot.message,
        )
        self._snapshots[snapshot_id] = deepcopy(saved_snapshot)
        self._snapshot_ids.append(snapshot_id)
        return snapshot_id

    def list_recent(self, *, limit: int = 50) -> list[SourceSnapshotMetadata]:
        return [
            deepcopy(self._snapshots[snapshot_id])
            for snapshot_id in reversed(self._snapshot_ids[-limit:])
        ]


class PostgresSourceSnapshotRepository:
    def __init__(self, *, database_url: str, connect_factory=None):
        self.database_url = database_url
        self.connect_factory = connect_factory

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists source_snapshots (
                        id text primary key,
                        payload jsonb not null,
                        created_at timestamptz not null default now()
                    )
                    """
                )

    def save(self, snapshot: SourceSnapshotMetadata) -> str:
        snapshot_id = snapshot.id or str(uuid4())
        payload = _snapshot_payload(
            SourceSnapshotMetadata(
                id=snapshot_id,
                source_name=snapshot.source_name,
                category=snapshot.category,
                status=snapshot.status,
                path=snapshot.path,
                content_hash=snapshot.content_hash,
                item_count=snapshot.item_count,
                fact_count=snapshot.fact_count,
                match_count=snapshot.match_count,
                message=snapshot.message,
            )
        )

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into source_snapshots (id, payload)
                    values (%s, %s)
                    on conflict (id) do update
                    set payload = excluded.payload
                    """,
                    (snapshot_id, _json_payload(payload)),
                )

        return snapshot_id

    def list_recent(self, *, limit: int = 50) -> list[SourceSnapshotMetadata]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select payload from source_snapshots
                    order by created_at desc
                    limit %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()

        return [_snapshot_from_payload(dict(row[0])) for row in rows]

    def _connect(self):
        if self.connect_factory is not None:
            return self.connect_factory()

        import psycopg

        return psycopg.connect(self.database_url)


def default_source_snapshot_repository() -> SourceSnapshotRepository:
    repository_kind = os.getenv("SOURCE_SNAPSHOT_REPOSITORY", "memory")
    if repository_kind == "postgres":
        repository = PostgresSourceSnapshotRepository(
            database_url=os.environ["DATABASE_URL"]
        )
        repository.ensure_schema()
        return repository

    return InMemorySourceSnapshotRepository()


def _snapshot_payload(snapshot: SourceSnapshotMetadata) -> dict:
    return {
        "id": snapshot.id,
        "source_name": snapshot.source_name,
        "category": snapshot.category,
        "status": snapshot.status,
        "path": snapshot.path,
        "content_hash": snapshot.content_hash,
        "item_count": snapshot.item_count,
        "fact_count": snapshot.fact_count,
        "match_count": snapshot.match_count,
        "message": snapshot.message,
    }


def _snapshot_from_payload(payload: dict) -> SourceSnapshotMetadata:
    return SourceSnapshotMetadata(
        id=payload["id"],
        source_name=payload["source_name"],
        category=payload.get("category"),
        status=payload["status"],
        path=payload["path"],
        content_hash=payload["content_hash"],
        item_count=int(payload["item_count"]),
        fact_count=int(payload["fact_count"]),
        match_count=int(payload["match_count"]),
        message=payload.get("message"),
    )


def _json_payload(payload: dict):
    try:
        from psycopg.types.json import Json
    except ModuleNotFoundError:
        return payload

    return Json(payload)
