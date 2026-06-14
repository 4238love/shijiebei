from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.ai_reports import AIAnalysisReport, AIProviderConfig, generate_ai_analysis_report
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
async def create_ai_report(payload: CreateAIReportRequest):
    provider = _provider(payload.provider_name)
    report = generate_ai_analysis_report(
        prediction=_prediction(payload.prediction),
        provider=provider,
        validated_facts=[_validated_fact(fact) for fact in payload.validated_facts],
    )
    return _report_response(report)


def _provider(provider_name: str) -> TemplateAIReportProvider:
    if provider_name == "deepseek":
        return TemplateAIReportProvider(AIProviderConfig.deepseek())
    if provider_name == "gpt":
        return TemplateAIReportProvider(AIProviderConfig.gpt())

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Only deepseek and gpt providers are supported",
    )


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


def _report_response(report: AIAnalysisReport) -> AIReportResponse:
    return AIReportResponse(
        provider_name=report.provider_name,
        model_name=report.model_name,
        content=report.content,
        input_summary=report.input_summary,
    )
