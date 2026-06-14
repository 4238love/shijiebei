from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.ai_report_repository import AIReportRepository
from app.ai_reports import (
    AIAnalysisReport,
    AIProviderConfig,
    OpenAICompatibleAIReportProvider,
    generate_ai_analysis_report,
)
from app.cross_source_validation import ConflictStatus, ValidatedFact
from app.prediction_engine import MatchPrediction, ScorelineProbability

router = APIRouter(prefix="/ai-reports", tags=["ai-reports"])


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


class ValidatedFactPayload(BaseModel):
    fact_type: str
    entity_key: str
    status: ConflictStatus
    value: Any | None
    sources: list[str] = Field(default_factory=list)
    conflicting_values: dict[Any, list[str]] = Field(default_factory=dict)


class CreateAIReportRequest(BaseModel):
    provider_name: str
    prediction: MatchPredictionPayload
    validated_facts: list[ValidatedFactPayload] = Field(default_factory=list)


class AIReportResponse(BaseModel):
    id: str
    provider_name: str
    model_name: str
    content: str
    input_summary: dict


class TemplateAIReportProvider:
    def __init__(self, config: AIProviderConfig):
        self.provider_name = config.provider_name
        self.model_name = config.model_name

    def generate_report(self, payload: dict) -> str:
        probabilities = payload["probabilities"]
        strongest_outcome = max(probabilities.items(), key=lambda item: item[1])[0]
        return (
            f"{payload['match']} report from {self.provider_name}/{self.model_name}: "
            f"strongest statistical outcome is {strongest_outcome}; "
            f"confidence level {payload['confidence_level']}; "
            f"{len(payload['conflict_statuses'])} validated source facts reviewed."
        )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AIReportResponse)
async def create_ai_report(payload: CreateAIReportRequest, request: Request):
    provider = _provider(payload.provider_name)
    report = generate_ai_analysis_report(
        prediction=_prediction(payload.prediction),
        provider=provider,
        validated_facts=[_validated_fact(fact) for fact in payload.validated_facts],
    )
    response = _report_response(report, report_id=str(uuid4()))
    _ai_report_repository(request).save(response.model_dump())
    return response


@router.get("/{report_id}", response_model=AIReportResponse)
async def get_ai_report(report_id: str, request: Request):
    report = _ai_report_repository(request).get(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI report not found",
        )

    return report


def _provider(provider_name: str):
    if provider_name == "deepseek":
        config = AIProviderConfig.deepseek()
    elif provider_name == "gpt":
        config = AIProviderConfig.gpt()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only deepseek and gpt providers are supported",
        )

    if os.getenv("AI_REPORT_MODE") == "live":
        return OpenAICompatibleAIReportProvider(config)

    return TemplateAIReportProvider(config)


def _prediction(payload: MatchPredictionPayload) -> MatchPrediction:
    return MatchPrediction(
        home_team=payload.home_team,
        away_team=payload.away_team,
        weight_version=payload.weight_version,
        simulation_count=payload.simulation_count,
        expected_goals=payload.expected_goals,
        probabilities=payload.probabilities,
        top_scorelines=tuple(
            ScorelineProbability(
                home_goals=scoreline.home_goals,
                away_goals=scoreline.away_goals,
                probability=scoreline.probability,
            )
            for scoreline in payload.top_scorelines
        ),
        confidence_level=payload.confidence_level,
    )


def _validated_fact(payload: ValidatedFactPayload) -> ValidatedFact:
    return ValidatedFact(
        fact_type=payload.fact_type,
        entity_key=payload.entity_key,
        status=payload.status,
        value=payload.value,
        sources=payload.sources,
        conflicting_values=payload.conflicting_values,
    )


def _report_response(report: AIAnalysisReport, *, report_id: str) -> AIReportResponse:
    return AIReportResponse(
        id=report_id,
        provider_name=report.provider_name,
        model_name=report.model_name,
        content=report.content,
        input_summary=report.input_summary,
    )


def _ai_report_repository(request: Request) -> AIReportRepository:
    return request.app.state.ai_report_repository
