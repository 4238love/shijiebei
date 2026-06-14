from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.prediction_engine import WeightVersion
from app.weights import (
    WeightRecommendation,
    WeightRecommendationRegistry,
    WeightRecommendationStatus,
)

router = APIRouter(prefix="/weights", tags=["weights"])


class WeightVersionResponse(BaseModel):
    name: str
    factors: dict[str, float]


class CreateWeightRecommendationRequest(BaseModel):
    provider_name: str
    proposed_factors: dict[str, float] = Field(default_factory=dict)
    rationale: str


class WeightRecommendationResponse(BaseModel):
    id: str
    provider_name: str
    proposed_factors: dict[str, float]
    rationale: str
    status: WeightRecommendationStatus
    reviewer: str | None
    backtest_reference: str | None
    activated_version_name: str | None


class ApproveWeightRecommendationRequest(BaseModel):
    reviewer: str
    backtest_reference: str
    new_version_name: str


def create_weight_registry() -> WeightRecommendationRegistry:
    return WeightRecommendationRegistry(
        active_weight_version=WeightVersion(
            name="baseline",
            factors={"base_goal_rate": 1.35},
        )
    )


@router.get("/active", response_model=WeightVersionResponse)
async def get_active_weight_version(request: Request):
    active = _registry(request).active_weight_version
    return WeightVersionResponse(name=active.name, factors=active.factors)


@router.post(
    "/recommendations",
    status_code=status.HTTP_201_CREATED,
    response_model=WeightRecommendationResponse,
)
async def create_weight_recommendation(
    payload: CreateWeightRecommendationRequest,
    request: Request,
):
    recommendation = _registry(request).create_recommendation(
        provider_name=payload.provider_name,
        proposed_factors=payload.proposed_factors,
        rationale=payload.rationale,
    )
    return _recommendation_response(recommendation)


@router.get(
    "/recommendations/{recommendation_id}",
    response_model=WeightRecommendationResponse,
)
async def get_weight_recommendation(recommendation_id: str, request: Request):
    try:
        recommendation = _registry(request).get_recommendation(recommendation_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weight recommendation not found",
        ) from error

    return _recommendation_response(recommendation)


@router.post(
    "/recommendations/{recommendation_id}/approve",
    response_model=WeightVersionResponse,
)
async def approve_weight_recommendation(
    recommendation_id: str,
    payload: ApproveWeightRecommendationRequest,
    request: Request,
):
    try:
        activated = _registry(request).approve_recommendation(
            recommendation_id=recommendation_id,
            reviewer=payload.reviewer,
            backtest_reference=payload.backtest_reference,
            new_version_name=payload.new_version_name,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weight recommendation not found",
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    return WeightVersionResponse(name=activated.name, factors=activated.factors)


def _registry(request: Request) -> WeightRecommendationRegistry:
    return request.app.state.weight_registry


def _recommendation_response(
    recommendation: WeightRecommendation,
) -> WeightRecommendationResponse:
    return WeightRecommendationResponse(
        id=recommendation.id,
        provider_name=recommendation.provider_name,
        proposed_factors=recommendation.proposed_factors,
        rationale=recommendation.rationale,
        status=recommendation.status,
        reviewer=recommendation.reviewer,
        backtest_reference=recommendation.backtest_reference,
        activated_version_name=recommendation.activated_version_name,
    )
