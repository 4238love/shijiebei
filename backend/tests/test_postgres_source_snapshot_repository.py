from app.source_snapshot_repository import (
    PostgresSourceSnapshotRepository,
    SourceSnapshotMetadata,
)


class FakeCursor:
    def __init__(self, fetchall_result=None):
        self.statements = []
        self.fetchall_result = fetchall_result or []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))

    def fetchall(self):
        return self.fetchall_result


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_instance


def snapshot_metadata() -> SourceSnapshotMetadata:
    return SourceSnapshotMetadata(
        id="snapshot-1",
        source_name="espn-world-cup-scoreboard",
        category="schedule",
        status="ingested",
        path=".scratch/source-snapshots/espn.json",
        content_hash="abc123",
        item_count=1,
        fact_count=1,
        match_count=1,
        message=None,
    )


def test_postgres_source_snapshot_repository_creates_schema():
    cursor = FakeCursor()
    repository = PostgresSourceSnapshotRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    repository.ensure_schema()

    assert "create table if not exists source_snapshots" in cursor.statements[0][
        0
    ].lower()


def test_postgres_source_snapshot_repository_saves_metadata_payload():
    cursor = FakeCursor()
    repository = PostgresSourceSnapshotRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    snapshot_id = repository.save(snapshot_metadata())

    statement, params = cursor.statements[0]
    assert snapshot_id == "snapshot-1"
    assert "insert into source_snapshots" in statement.lower()
    assert params[0] == "snapshot-1"


def test_postgres_source_snapshot_repository_lists_recent_metadata():
    cursor = FakeCursor(
        fetchall_result=[
            (
                {
                    "id": "snapshot-1",
                    "source_name": "espn-world-cup-scoreboard",
                    "category": "schedule",
                    "status": "ingested",
                    "path": ".scratch/source-snapshots/espn.json",
                    "content_hash": "abc123",
                    "item_count": 1,
                    "fact_count": 1,
                    "match_count": 1,
                    "message": None,
                },
            )
        ]
    )
    repository = PostgresSourceSnapshotRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.list_recent(limit=5) == [snapshot_metadata()]
    assert cursor.statements[0][1] == (5,)
