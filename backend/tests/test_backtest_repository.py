from app.backtest_repository import InMemoryBacktestRepository


def test_in_memory_backtest_repository_saves_and_retrieves_run():
    repository = InMemoryBacktestRepository()

    backtest_id = repository.save({"match_count": 2})

    assert repository.get(backtest_id) == {"id": backtest_id, "match_count": 2}


def test_in_memory_backtest_repository_returns_none_for_missing_run():
    repository = InMemoryBacktestRepository()

    assert repository.get("missing") is None
