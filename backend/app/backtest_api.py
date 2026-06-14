from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.backtesting import ActualResult, BacktestCase, run_backtest
from app.cross_source_validation import ConflictStatus
from app.prediction_engine import MatchPrediction, ScorelineProbability

router = APIRouter(prefix="/backtests", tags=["backtests"])


class ScorelinePayload(BaseModel):
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    probability: float = Field(ge=0, le=1)


class MatchPredictionPayload(BaseModel):
    home_team: str
    away_team: str
    weight_version: str
    simulation_count: int = Field(gt=0)
    expected_goals: dict[str, float]
    probabilities: dict[str, float]
    top_scorelines: list[ScorelinePayload]
    confidence_level: str


class ActualResultPayload(BaseModel):
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)


class BacktestCasePayload(BaseModel):
    prediction: MatchPredictionPayload
    actual_result: ActualResultPayload
    conflict_status: ConflictStatus


class CreateBacktestRequest(BaseModel):
    cases: list[BacktestCasePayload]
    scoreline_top_n: int = Field(default=5, gt=0)


class BacktestSegmentResponse(BaseModel):
    match_count: int
    outcome_hit_rate: float


class BacktestRunResponse(BaseModel):
    id: str
    match_count: int
    outcome_hit_rate: float
    brier_score: float
    log_loss: float
    scoreline_top_n_hit_rate: float
    segments: dict[str, BacktestSegmentResponse]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BacktestRunResponse)
async def create_backtest(payload: CreateBacktestRequest, request: Request):
    try:
        run = run_backtest(
            [_backtest_case(case) for case in payload.cases],
            scoreline_top_n=payload.scoreline_top_n,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    response = BacktestRunResponse(
        id=str(uuid4()),
        match_count=run.match_count,
        outcome_hit_rate=run.outcome_hit_rate,
        brier_score=run.brier_score,
        log_loss=run.log_loss,
        scoreline_top_n_hit_rate=run.scoreline_top_n_hit_rate,
        segments={
            key: BacktestSegmentResponse(
                match_count=segment.match_count,
                outcome_hit_rate=segment.outcome_hit_rate,
            )
            for key, segment in run.segments.items()
        },
    )
    _backtest_runs(request)[response.id] = response.model_dump()
    return response


@router.get("/{backtest_id}", response_model=BacktestRunResponse)
async def get_backtest(backtest_id: str, request: Request):
    run = _backtest_runs(request).get(backtest_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found",
        )

    return run


def _backtest_case(payload: BacktestCasePayload) -> BacktestCase:
    return BacktestCase(
        prediction=MatchPrediction(
            home_team=payload.prediction.home_team,
            away_team=payload.prediction.away_team,
            weight_version=payload.prediction.weight_version,
            simulation_count=payload.prediction.simulation_count,
            expected_goals=payload.prediction.expected_goals,
            probabilities=payload.prediction.probabilities,
            top_scorelines=tuple(
                ScorelineProbability(
                    home_goals=scoreline.home_goals,
                    away_goals=scoreline.away_goals,
                    probability=scoreline.probability,
                )
                for scoreline in payload.prediction.top_scorelines
            ),
            confidence_level=payload.prediction.confidence_level,
        ),
        actual_result=ActualResult(
            home_goals=payload.actual_result.home_goals,
            away_goals=payload.actual_result.away_goals,
        ),
        conflict_status=payload.conflict_status,
    )


def _backtest_runs(request: Request) -> dict:
    return request.app.state.backtest_runs
