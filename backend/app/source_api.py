from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.cross_source_validation import (
    CrossSourceValidator,
    NormalizedFact,
    ValidatedFact,
)
from app.data_sources import ScheduleMatch, SourceIngestionResult, SourceSnapshot
from app.source_config import SourceDefinition, load_source_catalog_config
from app.source_ingestion import ingest_source_safely
from app.source_snapshot_repository import (
    SourceSnapshotMetadata,
    SourceSnapshotRepository,
)

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceResponse(BaseModel):
    category: str
    name: str
    url: str
    priority: int
    adapter: str
    notes: str


class SourcesResponse(BaseModel):
    missing_first_wave_categories: list[str]
    sources: list[SourceResponse]


class SourceIngestRequest(BaseModel):
    category: str | None = None
    source_name: str | None = None


class SourceSnapshotResponse(BaseModel):
    path: str
    content_hash: str


class SourceSnapshotMetadataResponse(BaseModel):
    id: str
    source_name: str
    category: str | None
    status: str
    path: str
    content_hash: str
    item_count: int
    fact_count: int
    match_count: int
    message: str | None


class ScheduleMatchResponse(BaseModel):
    source_name: str
    event_id: str
    home_team: str
    away_team: str
    kickoff_at: str | None
    status: str
    home_score: int | None
    away_score: int | None


class NormalizedFactResponse(BaseModel):
    fact_type: str
    entity_key: str
    value: Any
    source_name: str
    is_stale: bool


class SourceIngestionResultResponse(BaseModel):
    source_name: str
    category: str | None
    status: str
    item_count: int
    snapshot: SourceSnapshotResponse | None
    matches: list[ScheduleMatchResponse]
    facts: list[NormalizedFactResponse]
    message: str | None


class SourceIngestResponse(BaseModel):
    results: list[SourceIngestionResultResponse]


class SourceSnapshotsResponse(BaseModel):
    snapshots: list[SourceSnapshotMetadataResponse]


class ValidatedFactResponse(BaseModel):
    fact_type: str
    entity_key: str
    status: str
    value: Any | None
    sources: list[str]
    conflicting_values: dict[str, list[str]]


class SourceValidateResponse(BaseModel):
    results: list[SourceIngestionResultResponse]
    validated_facts: list[ValidatedFactResponse]


@router.get("", response_model=SourcesResponse)
async def list_sources(request: Request):
    config = load_source_catalog_config(_source_config_path(request))

    return SourcesResponse(
        missing_first_wave_categories=[
            category.value for category in config.catalog.missing_first_wave_categories()
        ],
        sources=[_source_response(source) for source in config.sources],
    )


@router.post("/ingest", response_model=SourceIngestResponse)
async def ingest_sources(payload: SourceIngestRequest, request: Request):
    config = load_source_catalog_config(_source_config_path(request))
    definitions = _matching_sources(
        config.sources,
        category=payload.category,
        source_name=payload.source_name,
    )
    if not definitions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching data sources found",
        )

    results = [
        ingest_source_safely(
            definition,
            snapshot_dir=_source_snapshot_dir(request),
            http_client=getattr(request.app.state, "source_http_client", None),
        )
        for definition in definitions
    ]
    _record_snapshot_metadata(request, results)
    return SourceIngestResponse(
        results=[_ingestion_result_response(result) for result in results]
    )


@router.get("/snapshots", response_model=SourceSnapshotsResponse)
async def list_source_snapshots(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
):
    return SourceSnapshotsResponse(
        snapshots=[
            _snapshot_metadata_response(snapshot)
            for snapshot in _source_snapshot_repository(request).list_recent(
                limit=limit
            )
        ]
    )


@router.post("/validate", response_model=SourceValidateResponse)
async def validate_sources(payload: SourceIngestRequest, request: Request):
    config = load_source_catalog_config(_source_config_path(request))
    definitions = _matching_sources(
        config.sources,
        category=payload.category,
        source_name=payload.source_name,
    )
    if not definitions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching data sources found",
        )

    results = [
        ingest_source_safely(
            definition,
            snapshot_dir=_source_snapshot_dir(request),
            http_client=getattr(request.app.state, "source_http_client", None),
        )
        for definition in definitions
    ]
    _record_snapshot_metadata(request, results)
    facts = [fact for result in results for fact in result.facts]

    return SourceValidateResponse(
        results=[_ingestion_result_response(result) for result in results],
        validated_facts=[
            _validated_fact_response(fact)
            for fact in _validate_facts(definitions, facts)
        ],
    )


def _source_config_path(request: Request) -> Path:
    return Path(request.app.state.source_config_path)


def _source_snapshot_dir(request: Request) -> Path:
    return Path(request.app.state.source_snapshot_dir)


def _source_snapshot_repository(request: Request) -> SourceSnapshotRepository:
    return request.app.state.source_snapshot_repository


def _matching_sources(
    sources: list[SourceDefinition],
    *,
    category: str | None,
    source_name: str | None,
) -> list[SourceDefinition]:
    return [
        source
        for source in sources
        if (category is None or source.category.value == category)
        and (source_name is None or source.name == source_name)
    ]


def _source_response(source: SourceDefinition) -> SourceResponse:
    return SourceResponse(
        category=source.category.value,
        name=source.name,
        url=source.url,
        priority=source.priority,
        adapter=source.adapter,
        notes=source.notes,
    )


def _ingestion_result_response(
    result: SourceIngestionResult,
) -> SourceIngestionResultResponse:
    return SourceIngestionResultResponse(
        source_name=result.source_name,
        category=result.category.value if result.category else None,
        status=result.status.value,
        item_count=result.item_count,
        snapshot=_snapshot_response(result.snapshot) if result.snapshot else None,
        matches=[_match_response(match) for match in result.matches],
        facts=[_fact_response(fact) for fact in result.facts],
        message=result.message,
    )


def _snapshot_response(snapshot: SourceSnapshot) -> SourceSnapshotResponse:
    return SourceSnapshotResponse(
        path=str(snapshot.path),
        content_hash=snapshot.content_hash,
    )


def _snapshot_metadata_response(
    snapshot: SourceSnapshotMetadata,
) -> SourceSnapshotMetadataResponse:
    return SourceSnapshotMetadataResponse(
        id=snapshot.id,
        source_name=snapshot.source_name,
        category=snapshot.category,
        status=snapshot.status,
        path=snapshot.path,
        content_hash=snapshot.content_hash,
        item_count=snapshot.item_count,
        fact_count=snapshot.fact_count,
        match_count=snapshot.match_count,
        message=snapshot.message,
    )


def _record_snapshot_metadata(
    request: Request,
    results: list[SourceIngestionResult],
) -> None:
    repository = _source_snapshot_repository(request)
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


def _match_response(match: ScheduleMatch) -> ScheduleMatchResponse:
    return ScheduleMatchResponse(
        source_name=match.source_name,
        event_id=match.event_id,
        home_team=match.home_team,
        away_team=match.away_team,
        kickoff_at=match.kickoff_at,
        status=match.status,
        home_score=match.home_score,
        away_score=match.away_score,
    )


def _fact_response(fact: NormalizedFact) -> NormalizedFactResponse:
    return NormalizedFactResponse(
        fact_type=fact.fact_type,
        entity_key=fact.entity_key,
        value=fact.value,
        source_name=fact.source_name,
        is_stale=fact.is_stale,
    )


def _validate_facts(
    definitions: list[SourceDefinition],
    facts: list[NormalizedFact],
) -> list[ValidatedFact]:
    if not facts:
        return []

    source_priority = {
        fact_type: _source_names_by_priority(definitions)
        for fact_type in {fact.fact_type for fact in facts}
    }
    validator = CrossSourceValidator(source_priority=source_priority)

    validated: list[ValidatedFact] = []
    for fact_type, entity_key in sorted(
        {(fact.fact_type, fact.entity_key) for fact in facts}
    ):
        validated.append(
            validator.validate(
                fact_type=fact_type,
                entity_key=entity_key,
                facts=facts,
            )
        )

    return validated


def _source_names_by_priority(definitions: list[SourceDefinition]) -> list[str]:
    return [
        definition.name
        for definition in sorted(definitions, key=lambda source: source.priority)
    ]


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
