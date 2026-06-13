from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.data_sources import ScheduleMatch, SourceIngestionResult, SourceSnapshot
from app.source_config import SourceDefinition, load_source_catalog_config
from app.source_ingestion import ingest_source_safely

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


class ScheduleMatchResponse(BaseModel):
    source_name: str
    event_id: str
    home_team: str
    away_team: str
    kickoff_at: str | None
    status: str
    home_score: int | None
    away_score: int | None


class SourceIngestionResultResponse(BaseModel):
    source_name: str
    category: str | None
    status: str
    item_count: int
    snapshot: SourceSnapshotResponse | None
    matches: list[ScheduleMatchResponse]
    message: str | None


class SourceIngestResponse(BaseModel):
    results: list[SourceIngestionResultResponse]


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
    return SourceIngestResponse(
        results=[_ingestion_result_response(result) for result in results]
    )


def _source_config_path(request: Request) -> Path:
    return Path(request.app.state.source_config_path)


def _source_snapshot_dir(request: Request) -> Path:
    return Path(request.app.state.source_snapshot_dir)


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
        message=result.message,
    )


def _snapshot_response(snapshot: SourceSnapshot) -> SourceSnapshotResponse:
    return SourceSnapshotResponse(
        path=str(snapshot.path),
        content_hash=snapshot.content_hash,
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
