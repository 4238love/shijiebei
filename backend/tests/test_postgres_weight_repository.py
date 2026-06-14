from app.prediction_engine import WeightVersion
from app.weight_repository import PostgresWeightRepository
from app.weights import WeightRecommendation, WeightRecommendationStatus


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


def test_postgres_weight_repository_creates_schema():
    cursor = FakeCursor()
    repository = PostgresWeightRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    repository.ensure_schema()

    statements = "\n".join(statement for statement, _ in cursor.statements).lower()
    assert "create table if not exists weight_recommendations" in statements
    assert "create table if not exists weight_versions" in statements


def test_postgres_weight_repository_saves_recommendation_payload():
    cursor = FakeCursor()
    repository = PostgresWeightRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    repository.save_recommendation(
        WeightRecommendation(
            id="recommendation-1",
            provider_name="deepseek",
            proposed_factors={"home_goal_multiplier": 1.03},
            rationale="Reviewed backtest drift.",
            status=WeightRecommendationStatus.PROPOSED,
        )
    )

    statement, params = cursor.statements[0]
    assert "insert into weight_recommendations" in statement.lower()
    assert params[0] == "recommendation-1"


def test_postgres_weight_repository_retrieves_recommendation_payload():
    cursor = FakeCursor(
        fetchone_result=(
            {
                "id": "recommendation-1",
                "provider_name": "gpt",
                "proposed_factors": {"base_goal_rate": 1.45},
                "rationale": "Reviewed backtest drift.",
                "status": "approved",
                "reviewer": "operator",
                "backtest_reference": "backtest-run-001",
                "activated_version_name": "baseline-calibrated",
            },
        )
    )
    repository = PostgresWeightRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    recommendation = repository.get_recommendation("recommendation-1")

    assert recommendation == WeightRecommendation(
        id="recommendation-1",
        provider_name="gpt",
        proposed_factors={"base_goal_rate": 1.45},
        rationale="Reviewed backtest drift.",
        status=WeightRecommendationStatus.APPROVED,
        reviewer="operator",
        backtest_reference="backtest-run-001",
        activated_version_name="baseline-calibrated",
    )


def test_postgres_weight_repository_saves_active_weight_version():
    cursor = FakeCursor()
    repository = PostgresWeightRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    repository.save_active_weight_version(
        WeightVersion(name="baseline-calibrated", factors={"base_goal_rate": 1.45})
    )

    statements = "\n".join(statement for statement, _ in cursor.statements).lower()
    assert "update weight_versions" in statements
    assert "insert into weight_versions" in statements


def test_postgres_weight_repository_retrieves_active_weight_version():
    cursor = FakeCursor(
        fetchone_result=(
            {"name": "baseline-calibrated", "factors": {"base_goal_rate": 1.45}},
        )
    )
    repository = PostgresWeightRepository(
        database_url="postgresql://prediction:test@postgres/prediction",
        connect_factory=lambda: FakeConnection(cursor),
    )

    assert repository.get_active_weight_version() == WeightVersion(
        name="baseline-calibrated",
        factors={"base_goal_rate": 1.45},
    )
