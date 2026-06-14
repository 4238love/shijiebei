from app.backtest_repository import PostgresBacktestRepository


class FakeCursor:
    def __init__(self, fetchone_result=None):
        self.statements = []
        self.fetchone_result = fetchone_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))

    def fetchone(self):
        return self.fetchone_result


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_instance


def test_postgres_backtest_repository_creates_schema():
    cursor = FakeCursor()
    repository = PostgresBacktestRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    repository.ensure_schema()

    assert "create table if not exists backtest_runs" in cursor.statements[0][
        0
    ].lower()


def test_postgres_backtest_repository_saves_payload():
    cursor = FakeCursor()
    repository = PostgresBacktestRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    backtest_id = repository.save({"id": "backtest-1", "match_count": 2})

    statement, params = cursor.statements[0]
    assert backtest_id == "backtest-1"
    assert "insert into backtest_runs" in statement.lower()
    assert params[0] == "backtest-1"


def test_postgres_backtest_repository_retrieves_payload():
    cursor = FakeCursor(fetchone_result=({"id": "backtest-1", "match_count": 2},))
    repository = PostgresBacktestRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.get("backtest-1") == {"id": "backtest-1", "match_count": 2}


def test_postgres_backtest_repository_returns_none_for_missing_run():
    cursor = FakeCursor(fetchone_result=None)
    repository = PostgresBacktestRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.get("missing") is None
