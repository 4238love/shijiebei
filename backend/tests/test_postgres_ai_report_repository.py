from app.ai_report_repository import PostgresAIReportRepository


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


def test_postgres_ai_report_repository_creates_schema():
    cursor = FakeCursor()
    repository = PostgresAIReportRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    repository.ensure_schema()

    assert "create table if not exists ai_reports" in cursor.statements[0][0].lower()


def test_postgres_ai_report_repository_saves_payload():
    cursor = FakeCursor()
    repository = PostgresAIReportRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    report_id = repository.save({"id": "report-1", "provider_name": "gpt"})

    statement, params = cursor.statements[0]
    assert report_id == "report-1"
    assert "insert into ai_reports" in statement.lower()
    assert params[0] == "report-1"


def test_postgres_ai_report_repository_retrieves_payload():
    cursor = FakeCursor(fetchone_result=({"id": "report-1", "content": "analysis"},))
    repository = PostgresAIReportRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.get("report-1") == {"id": "report-1", "content": "analysis"}


def test_postgres_ai_report_repository_returns_none_for_missing_report():
    cursor = FakeCursor(fetchone_result=None)
    repository = PostgresAIReportRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.get("missing") is None
