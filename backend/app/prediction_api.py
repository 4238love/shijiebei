from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.prediction_engine import (
    PredictionDataset,
    TeamModel,
    WeightVersion,
    run_match_prediction,
)
from app.prediction_repository import PredictionRepository

router = APIRouter(prefix="/predictions", tags=["predictions"])


class TeamModelPayload(BaseModel):
    attack_index: float = Field(gt=0)
    defense_weakness: float = Field(gt=0)


class PredictionDatasetPayload(BaseModel):
    home_team: str
    away_team: str
    home: TeamModelPayload
    away: TeamModelPayload
    home_advantage: float = Field(default=1.0, gt=0)
    conflict_count: int = Field(default=0, ge=0)


class WeightVersionPayload(BaseModel):
    name: str
    factors: dict[str, float] = Field(default_factory=dict)


class CreatePredictionRequest(BaseModel):
    dataset: PredictionDatasetPayload
    weight_version: WeightVersionPayload = Field(
        default_factory=lambda: WeightVersionPayload(name="baseline", factors={})
    )
    simulation_count: int = Field(default=10_000, gt=0)
    seed: int | None = None


class ScorelineResponse(BaseModel):
    home_goals: int
    away_goals: int
    probability: float


class PredictionResponse(BaseModel):
    id: str
    home_team: str
    away_team: str
    weight_version: str
    simulation_count: int
    expected_goals: dict[str, float]
    probabilities: dict[str, float]
    top_scorelines: list[ScorelineResponse]
    confidence_level: str


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PredictionResponse)
async def create_prediction(payload: CreatePredictionRequest, request: Request):
    prediction = run_match_prediction(
        PredictionDataset(
            home_team=payload.dataset.home_team,
            away_team=payload.dataset.away_team,
            home=TeamModel(
                attack_index=payload.dataset.home.attack_index,
                defense_weakness=payload.dataset.home.defense_weakness,
            ),
            away=TeamModel(
                attack_index=payload.dataset.away.attack_index,
                defense_weakness=payload.dataset.away.defense_weakness,
            ),
            home_advantage=payload.dataset.home_advantage,
            conflict_count=payload.dataset.conflict_count,
        ),
        WeightVersion(
            name=payload.weight_version.name,
            factors=payload.weight_version.factors,
        ),
        simulation_count=payload.simulation_count,
        seed=payload.seed,
    )

    prediction_id = str(uuid4())
    response = PredictionResponse(
        id=prediction_id,
        home_team=prediction.home_team,
        away_team=prediction.away_team,
        weight_version=prediction.weight_version,
        simulation_count=prediction.simulation_count,
        expected_goals=prediction.expected_goals,
        probabilities=prediction.probabilities,
        top_scorelines=[
            ScorelineResponse(
                home_goals=scoreline.home_goals,
                away_goals=scoreline.away_goals,
                probability=scoreline.probability,
            )
            for scoreline in prediction.top_scorelines
        ],
        confidence_level=prediction.confidence_level,
    )

    _prediction_repository(request).save(response.model_dump())
    return response


@router.get("/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(prediction_id: str, request: Request):
    prediction = _prediction_repository(request).get(prediction_id)
    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match prediction not found",
        )

    return prediction


def _prediction_repository(request: Request) -> PredictionRepository:
    return request.app.state.prediction_repository
