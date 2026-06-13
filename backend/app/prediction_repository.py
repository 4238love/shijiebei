from __future__ import annotations

from copy import deepcopy
from typing import Protocol
from uuid import uuid4


class PredictionRepository(Protocol):
    def save(self, prediction: dict) -> str:
        ...

    def get(self, prediction_id: str) -> dict | None:
        ...


class InMemoryPredictionRepository:
    def __init__(self):
        self._predictions: dict[str, dict] = {}

    def save(self, prediction: dict) -> str:
        prediction_id = prediction.get("id") or str(uuid4())
        saved_prediction = {"id": prediction_id, **prediction}
        self._predictions[prediction_id] = deepcopy(saved_prediction)
        return prediction_id

    def get(self, prediction_id: str) -> dict | None:
        prediction = self._predictions.get(prediction_id)
        if prediction is None:
            return None
        return deepcopy(prediction)
