from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

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


class SourceBackedPredictionResponse(BaseModel):
    prediction: PredictionResponse
    dataset: PredictionDatasetPayload
    source_summary: SourceBackedPredictionSummary


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
    _prediction_repository(request).save(response.model_dump())

    return SourceBackedPredictionResponse(
        prediction=response,
        dataset=_dataset_response(dataset),
        source_summary=SourceBackedPredictionSummary(
            ingested_source_count=len(results),
            snapshot_count=sum(1 for result in results if result.snapshot is not None),
            normalized_fact_count=len(normalized_facts),
            validated_fact_count=len(validated_facts),
            conflict_count=dataset.conflict_count,
        ),
    )


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
