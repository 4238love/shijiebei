from app.prediction_repository import PostgresPredictionRepository


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


def test_postgres_repository_creates_schema():
    cursor = FakeCursor()
    repository = PostgresPredictionRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    repository.ensure_schema()

    assert "create table if not exists predictions" in cursor.statements[0][0].lower()


def test_postgres_repository_saves_prediction_payload():
    cursor = FakeCursor()
    repository = PostgresPredictionRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    prediction_id = repository.save({"id": "prediction-1", "home_team": "Brazil"})

    statement, params = cursor.statements[0]
    assert prediction_id == "prediction-1"
    assert "insert into predictions" in statement.lower()
    assert params[0] == "prediction-1"


def test_postgres_repository_retrieves_prediction_payload():
    cursor = FakeCursor(fetchone_result=({"id": "prediction-1", "home_team": "Brazil"},))
    repository = PostgresPredictionRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.get("prediction-1") == {
        "id": "prediction-1",
        "home_team": "Brazil",
    }


def test_postgres_repository_returns_none_for_missing_prediction():
    cursor = FakeCursor(fetchone_result=None)
    repository = PostgresPredictionRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.get("missing") is None
