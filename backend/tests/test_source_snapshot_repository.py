from app.source_snapshot_repository import (
    InMemorySourceSnapshotRepository,
    SourceSnapshotMetadata,
)


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


def test_in_memory_source_snapshot_repository_saves_and_lists_metadata():
    repository = InMemorySourceSnapshotRepository()

    snapshot_id = repository.save(snapshot_metadata())

    snapshots = repository.list_recent()
    assert snapshot_id == "snapshot-1"
    assert snapshots == [snapshot_metadata()]


def test_in_memory_source_snapshot_repository_returns_most_recent_first():
    repository = InMemorySourceSnapshotRepository()
    first = snapshot_metadata()
    second = SourceSnapshotMetadata(
        id="snapshot-2",
        source_name="bbc-world-cup-football",
        category="news_sentiment",
        status="ingested",
        path=".scratch/source-snapshots/bbc.html",
        content_hash="def456",
        item_count=1,
        fact_count=1,
        match_count=0,
        message="Snapshot captured.",
    )

    repository.save(first)
    repository.save(second)

    assert repository.list_recent(limit=1) == [second]
