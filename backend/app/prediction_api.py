from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.ai_reports import (
    generate_ai_analysis_report,
    provider_for_name,
    UnknownAIReportProvider,
)
from app.cross_source_validation import CrossSourceValidator, NormalizedFact, ValidatedFact
from app.prediction_dataset_builder import build_prediction_dataset_from_validated_facts
from app.prediction_engine import (
    PredictionDataset,
    TeamModel,
    WeightVersion,
    run_match_prediction,
)
from app.prediction_repository import PredictionRepository
from app.source_config import SourceDefinition, load_source_catalog_config
from app.source_ingestion import ingest_source_safely
from app.source_snapshot_repository import SourceSnapshotMetadata

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


class CreatePredictionFromSourcesRequest(BaseModel):
    home_team: str
    away_team: str
    category: str | None = None
    source_name: str | None = None
    home_advantage: float = Field(default=1.0, gt=0)
    weight_version: WeightVersionPayload | None = None
    simulation_count: int = Field(default=10_000, gt=0)
    seed: int | None = None
    generate_ai_report: bool = False
    ai_report_provider: str | None = None


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


class SourceBackedPredictionSummary(BaseModel):
    ingested_source_count: int
    snapshot_count: int
    normalized_fact_count: int
    validated_fact_count: int
    conflict_count: int


class SourceEvidenceResponse(BaseModel):
    source_name: str
    category: str | None
    status: str
    snapshot_path: str | None
    content_hash: str | None
    item_count: int
    fact_count: int
    match_count: int
    message: str | None


class ValidatedFactResponse(BaseModel):
    fact_type: str
    entity_key: str
    status: str
    value: Any | None
    sources: list[str]
    conflicting_values: dict[str, list[str]] = Field(default_factory=dict)


class AIReportResponse(BaseModel):
    id: str
    provider_name: str
    model_name: str
    content: str
    input_summary: dict[str, Any]


class SourceBackedPredictionResponse(BaseModel):
    prediction: PredictionResponse
    dataset: PredictionDatasetPayload
    source_summary: SourceBackedPredictionSummary
    source_evidence: list[SourceEvidenceResponse] = Field(default_factory=list)
    validated_facts: list[ValidatedFactResponse] = Field(default_factory=list)
    ai_report: AIReportResponse | None = None


class PredictionHistoryItemResponse(BaseModel):
    id: str
    home_team: str
    away_team: str
    probabilities: dict[str, float]
    confidence_level: str
    source_summary: SourceBackedPredictionSummary | None = None


class PredictionHistoryResponse(BaseModel):
    predictions: list[PredictionHistoryItemResponse]


class PredictionRecordResponse(BaseModel):
    prediction: PredictionResponse
    dataset: PredictionDatasetPayload | None = None
    source_summary: SourceBackedPredictionSummary | None = None
    source_evidence: list[SourceEvidenceResponse] = Field(default_factory=list)
    validated_facts: list[ValidatedFactResponse] = Field(default_factory=list)
    ai_report: AIReportResponse | None = None


@router.get("", response_model=PredictionHistoryResponse)
async def list_predictions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
):
    records = _prediction_repository(request).list_recent(limit=limit)
    return PredictionHistoryResponse(
        predictions=[_history_item_response(record) for record in records]
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PredictionResponse)
async def create_prediction(payload: CreatePredictionRequest, request: Request):
    prediction = run_match_prediction(
        _dataset_from_payload(payload.dataset),
        WeightVersion(
            name=payload.weight_version.name,
            factors=payload.weight_version.factors,
        ),
        simulation_count=payload.simulation_count,
        seed=payload.seed,
    )

    prediction_id = str(uuid4())
    response = _prediction_response(prediction, prediction_id=prediction_id)

    _prediction_repository(request).save(response.model_dump())
    return response


@router.post(
    "/from-sources",
    status_code=status.HTTP_201_CREATED,
    response_model=SourceBackedPredictionResponse,
)
async def create_prediction_from_sources(
    payload: CreatePredictionFromSourcesRequest,
    request: Request,
):
    definitions = _matching_source_definitions(request, payload)
    if not definitions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching data sources found",
        )

    results = [
        ingest_source_safely(
            definition,
            snapshot_dir=request.app.state.source_snapshot_dir,
            http_client=getattr(request.app.state, "source_http_client", None),
        )
        for definition in definitions
    ]
    _record_snapshot_metadata(request, results)
    normalized_facts = [fact for result in results for fact in result.facts]
    validated_facts = _validate_facts(definitions, normalized_facts)
    dataset = build_prediction_dataset_from_validated_facts(
        home_team=payload.home_team,
        away_team=payload.away_team,
        validated_facts=validated_facts,
        home_advantage=payload.home_advantage,
    )
    weight_version = _weight_version_from_request_or_active(payload, request)
    prediction = run_match_prediction(
        dataset,
        weight_version,
        simulation_count=payload.simulation_count,
        seed=payload.seed,
    )
    response = _prediction_response(prediction, prediction_id=str(uuid4()))
    dataset_response = _dataset_response(dataset)
    source_summary = SourceBackedPredictionSummary(
        ingested_source_count=len(results),
        snapshot_count=sum(1 for result in results if result.snapshot is not None),
        normalized_fact_count=len(normalized_facts),
        validated_fact_count=len(validated_facts),
        conflict_count=dataset.conflict_count,
    )
    source_evidence = [_source_evidence_response(result) for result in results]
    validated_fact_responses = [
        _validated_fact_response(fact) for fact in validated_facts
    ]
    ai_report = _create_optional_ai_report(
        payload=payload,
        prediction=prediction,
        validated_facts=validated_facts,
        request=request,
    )
    _prediction_repository(request).save(
        {
            **response.model_dump(),
            "dataset": dataset_response.model_dump(),
            "source_summary": source_summary.model_dump(),
            "source_evidence": [
                evidence.model_dump() for evidence in source_evidence
            ],
            "validated_facts": [
                fact.model_dump() for fact in validated_fact_responses
            ],
            "ai_report": ai_report.model_dump() if ai_report else None,
        }
    )

    return SourceBackedPredictionResponse(
        prediction=response,
        dataset=dataset_response,
        source_summary=source_summary,
        source_evidence=source_evidence,
        validated_facts=validated_fact_responses,
        ai_report=ai_report,
    )


@router.get("/{prediction_id}/record", response_model=PredictionRecordResponse)
async def get_prediction_record(prediction_id: str, request: Request):
    record = _prediction_repository(request).get(prediction_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match prediction not found",
        )

    return _prediction_record_response(record)


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


def _dataset_from_payload(payload: PredictionDatasetPayload) -> PredictionDataset:
    return PredictionDataset(
        home_team=payload.home_team,
        away_team=payload.away_team,
        home=TeamModel(
            attack_index=payload.home.attack_index,
            defense_weakness=payload.home.defense_weakness,
        ),
        away=TeamModel(
            attack_index=payload.away.attack_index,
            defense_weakness=payload.away.defense_weakness,
        ),
        home_advantage=payload.home_advantage,
        conflict_count=payload.conflict_count,
    )


def _dataset_response(dataset: PredictionDataset) -> PredictionDatasetPayload:
    return PredictionDatasetPayload(
        home_team=dataset.home_team,
        away_team=dataset.away_team,
        home=TeamModelPayload(
            attack_index=dataset.home.attack_index,
            defense_weakness=dataset.home.defense_weakness,
        ),
        away=TeamModelPayload(
            attack_index=dataset.away.attack_index,
            defense_weakness=dataset.away.defense_weakness,
        ),
        home_advantage=dataset.home_advantage,
        conflict_count=dataset.conflict_count,
    )


def _prediction_response(prediction, *, prediction_id: str) -> PredictionResponse:
    return PredictionResponse(
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


def _history_item_response(record: dict) -> PredictionHistoryItemResponse:
    return PredictionHistoryItemResponse(
        id=record["id"],
        home_team=record["home_team"],
        away_team=record["away_team"],
        probabilities=record["probabilities"],
        confidence_level=record["confidence_level"],
        source_summary=(
            SourceBackedPredictionSummary(**record["source_summary"])
            if record.get("source_summary")
            else None
        ),
    )


def _prediction_record_response(record: dict) -> PredictionRecordResponse:
    return PredictionRecordResponse(
        prediction=PredictionResponse(**record),
        dataset=(
            PredictionDatasetPayload(**record["dataset"])
            if record.get("dataset")
            else None
        ),
        source_summary=(
            SourceBackedPredictionSummary(**record["source_summary"])
            if record.get("source_summary")
            else None
        ),
        source_evidence=[
            SourceEvidenceResponse(**evidence)
            for evidence in record.get("source_evidence", [])
        ],
        validated_facts=[
            ValidatedFactResponse(**fact)
            for fact in record.get("validated_facts", [])
        ],
        ai_report=(
            AIReportResponse(**record["ai_report"])
            if record.get("ai_report")
            else None
        ),
    )


def _create_optional_ai_report(
    *,
    payload: CreatePredictionFromSourcesRequest,
    prediction,
    validated_facts: list[ValidatedFact],
    request: Request,
) -> AIReportResponse | None:
    if not payload.generate_ai_report and payload.ai_report_provider is None:
        return None

    provider_name = payload.ai_report_provider or "gpt"
    try:
        provider = provider_for_name(provider_name)
    except UnknownAIReportProvider as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    report = generate_ai_analysis_report(
        prediction=prediction,
        provider=provider,
        validated_facts=validated_facts,
    )
    response = AIReportResponse(
        id=str(uuid4()),
        provider_name=report.provider_name,
        model_name=report.model_name,
        content=report.content,
        input_summary=report.input_summary,
    )
    request.app.state.ai_report_repository.save(response.model_dump())
    return response


def _source_evidence_response(result) -> SourceEvidenceResponse:
    return SourceEvidenceResponse(
        source_name=result.source_name,
        category=result.category.value if result.category else None,
        status=result.status.value,
        snapshot_path=str(result.snapshot.path) if result.snapshot else None,
        content_hash=result.snapshot.content_hash if result.snapshot else None,
        item_count=result.item_count,
        fact_count=len(result.facts),
        match_count=len(result.matches),
        message=result.message,
    )


def _validated_fact_response(fact: ValidatedFact) -> ValidatedFactResponse:
    return ValidatedFactResponse(
        fact_type=fact.fact_type,
        entity_key=fact.entity_key,
        status=fact.status.value,
        value=fact.value,
        sources=fact.sources,
        conflicting_values={
            str(value): sources for value, sources in fact.conflicting_values.items()
        },
    )


def _weight_version_from_request_or_active(
    payload: CreatePredictionFromSourcesRequest,
    request: Request,
) -> WeightVersion:
    if payload.weight_version is not None:
        return WeightVersion(
            name=payload.weight_version.name,
            factors=payload.weight_version.factors,
        )

    return request.app.state.weight_registry.active_weight_version


def _matching_source_definitions(
    request: Request,
    payload: CreatePredictionFromSourcesRequest,
) -> list[SourceDefinition]:
    config = load_source_catalog_config(request.app.state.source_config_path)
    return [
        source
        for source in config.sources
        if (payload.category is None or source.category.value == payload.category)
        and (payload.source_name is None or source.name == payload.source_name)
    ]


def _validate_facts(
    definitions: list[SourceDefinition],
    facts: list[NormalizedFact],
) -> list[ValidatedFact]:
    if not facts:
        return []

    source_priority = {
        fact_type: [
            definition.name
            for definition in sorted(definitions, key=lambda source: source.priority)
        ]
        for fact_type in {fact.fact_type for fact in facts}
    }
    validator = CrossSourceValidator(source_priority=source_priority)

    return [
        validator.validate(
            fact_type=fact_type,
            entity_key=entity_key,
            facts=facts,
        )
        for fact_type, entity_key in sorted(
            {(fact.fact_type, fact.entity_key) for fact in facts}
        )
    ]


def _record_snapshot_metadata(request: Request, results) -> None:
    repository = request.app.state.source_snapshot_repository
    for result in results:
        if result.snapshot is None:
            continue
        repository.save(
            SourceSnapshotMetadata(
                id="",
                source_name=result.source_name,
                category=result.category.value if result.category else None,
                status=result.status.value,
                path=str(result.snapshot.path),
                content_hash=result.snapshot.content_hash,
                item_count=result.item_count,
                fact_count=len(result.facts),
                match_count=len(result.matches),
                message=result.message,
            )
        )
