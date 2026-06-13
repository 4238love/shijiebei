from app.prediction_repository import InMemoryPredictionRepository


def test_in_memory_prediction_repository_saves_and_retrieves_prediction():
    repository = InMemoryPredictionRepository()

    prediction_id = repository.save({"home_team": "Brazil"})

    assert prediction_id
    assert repository.get(prediction_id) == {"id": prediction_id, "home_team": "Brazil"}


def test_in_memory_prediction_repository_returns_none_for_missing_prediction():
    repository = InMemoryPredictionRepository()

    assert repository.get("missing") is None
