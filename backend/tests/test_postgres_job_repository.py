from app.job_repository import JobRunRecord, PostgresJobRunRepository


class FakeCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None):
        self.statements = []
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))

    def fetchone(self):
        return self.fetchone_result

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


def job_run() -> JobRunRecord:
    return JobRunRecord(
        id="run-1",
        job_id="validate-sources",
        status="succeeded",
        started_at="2026-06-14T00:00:00+00:00",
        finished_at="2026-06-14T00:00:01+00:00",
        summary={"source_count": 1},
    )


def test_postgres_job_run_repository_creates_schema():
    cursor = FakeCursor()
    repository = PostgresJobRunRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    repository.ensure_schema()

    assert "create table if not exists job_runs" in cursor.statements[0][0].lower()


def test_postgres_job_run_repository_saves_run_payload():
    cursor = FakeCursor()
    repository = PostgresJobRunRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    run_id = repository.save(job_run())

    statement, params = cursor.statements[0]
    assert run_id == "run-1"
    assert "insert into job_runs" in statement.lower()
    assert params[0] == "run-1"
    assert params[1] == "validate-sources"
    assert params[2] == "succeeded"


def test_postgres_job_run_repository_lists_recent_runs():
    cursor = FakeCursor(
        fetchall_result=[
            (
                {
                    "id": "run-1",
                    "job_id": "validate-sources",
                    "status": "succeeded",
                    "started_at": "2026-06-14T00:00:00+00:00",
                    "finished_at": "2026-06-14T00:00:01+00:00",
                    "summary": {"source_count": 1},
                    "error": None,
                },
            )
        ]
    )
    repository = PostgresJobRunRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.list_recent(limit=5) == [job_run()]
    statement, params = cursor.statements[0]
    assert "order by started_at desc" in statement.lower()
    assert params == (5,)


def test_postgres_job_run_repository_counts_runs_by_job():
    cursor = FakeCursor(fetchone_result=(2,))
    repository = PostgresJobRunRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.count_by_job("validate-sources") == 2
    assert cursor.statements[0][1] == ("validate-sources",)


def test_postgres_job_run_repository_finds_last_run_by_job():
    cursor = FakeCursor(
        fetchone_result=(
            {
                "id": "run-1",
                "job_id": "validate-sources",
                "status": "succeeded",
                "started_at": "2026-06-14T00:00:00+00:00",
                "finished_at": "2026-06-14T00:00:01+00:00",
                "summary": {"source_count": 1},
                "error": None,
            },
        )
    )
    repository = PostgresJobRunRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.last_for_job("validate-sources") == job_run()
    statement, params = cursor.statements[0]
    assert "where job_id = %s" in statement.lower()
    assert params == ("validate-sources",)


def test_postgres_job_run_repository_returns_none_when_last_run_missing():
    cursor = FakeCursor(fetchone_result=None)
    repository = PostgresJobRunRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.last_for_job("missing") is None
