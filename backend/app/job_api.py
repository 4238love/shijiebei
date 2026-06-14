from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.cross_source_validation import CrossSourceValidator, NormalizedFact, ValidatedFact
from app.job_repository import JobRunRecord, JobRunRepository
from app.job_runner import InMemoryJobRunner, JobDefinition, JobState
from app.prediction_dataset_builder import build_prediction_dataset_from_validated_facts
from app.prediction_engine import run_match_prediction
from app.source_config import SourceDefinition, load_source_catalog_config
from app.source_ingestion import ingest_source_safely
from app.source_snapshot_repository import SourceSnapshotMetadata

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobRunResponse(BaseModel):
    id: str
    job_id: str
    status: str
    started_at: str
    finished_at: str
    summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    label: str
    interval_minutes: int
    run_count: int
    last_run: JobRunResponse | None = None


class SchedulerStatusResponse(BaseModel):
    enabled: bool
    running: bool
    job_count: int
    job_ids: list[str]


class JobsResponse(BaseModel):
    jobs: list[JobStatusResponse]
    recent_runs: list[JobRunResponse]
    scheduler: SchedulerStatusResponse


@router.get("", response_model=JobsResponse)
async def list_jobs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
):
    runner = _job_runner(request)
    return JobsResponse(
        jobs=[_job_status_response(state) for state in runner.list_states()],
        recent_runs=[
            _job_run_response(record) for record in runner.recent_runs(limit=limit)
        ],
        scheduler=_scheduler_status_response(request.app.state.pipeline_scheduler),
    )


@router.post("/{job_id}/run", response_model=JobRunResponse)
async def run_job(job_id: str, request: Request):
    try:
        record = _job_runner(request).run(job_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return _job_run_response(record)


def create_job_runner(
    app,
    job_run_repository: JobRunRepository | None = None,
) -> InMemoryJobRunner:
    return InMemoryJobRunner(
        [
            JobDefinition(
                job_id="ingest-sources",
                label="Ingest configured sources",
                interval_minutes=30,
                handler=lambda: _ingest_sources_job(app),
            ),
            JobDefinition(
                job_id="validate-sources",
                label="Validate source facts",
                interval_minutes=30,
                handler=lambda: _validate_sources_job(app),
            ),
            JobDefinition(
                job_id="create-source-backed-prediction",
                label="Create source-backed prediction",
                interval_minutes=60,
                handler=lambda: _create_source_backed_prediction_job(app),
            ),
        ],
        run_repository=job_run_repository,
    )


def _job_runner(request: Request) -> InMemoryJobRunner:
    return request.app.state.job_runner


def _job_status_response(state: JobState) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=state.job_id,
        label=state.label,
        interval_minutes=state.interval_minutes,
        run_count=state.run_count,
        last_run=_job_run_response(state.last_run) if state.last_run else None,
    )


def _job_run_response(record: JobRunRecord) -> JobRunResponse:
    return JobRunResponse(
        id=record.id,
        job_id=record.job_id,
        status=record.status,
        started_at=record.started_at,
        finished_at=record.finished_at,
        summary=record.summary,
        error=record.error,
    )


def _scheduler_status_response(scheduler) -> SchedulerStatusResponse:
    status = scheduler.status()
    return SchedulerStatusResponse(
        enabled=status.enabled,
        running=status.running,
        job_count=status.job_count,
        job_ids=status.job_ids,
    )


def _ingest_sources_job(app) -> dict:
    definitions = _load_source_definitions(app)
    results = _ingest_definitions(app, definitions)
    _record_snapshot_metadata(app, results)
    return _source_results_summary(results)


def _validate_sources_job(app) -> dict:
    definitions = _load_source_definitions(app)
    results = _ingest_definitions(app, definitions)
    _record_snapshot_metadata(app, results)
    facts = [fact for result in results for fact in result.facts]
    validated_facts = _validate_facts(definitions, facts)
    return {
        **_source_results_summary(results),
        "validated_fact_count": len(validated_facts),
        "conflicting_fact_count": sum(
            1 for fact in validated_facts if fact.status.value == "conflicting"
        ),
    }


def _create_source_backed_prediction_job(app) -> dict:
    home_team = os.getenv("JOB_HOME_TEAM", "Brazil")
    away_team = os.getenv("JOB_AWAY_TEAM", "Croatia")
    category = os.getenv("JOB_SOURCE_CATEGORY", "ranking") or None
    simulation_count = int(os.getenv("JOB_SIMULATION_COUNT", "1000"))

    definitions = _load_source_definitions(app, category=category)
    if not definitions:
        raise RuntimeError("No matching data sources found for prediction job")

    results = _ingest_definitions(app, definitions)
    _record_snapshot_metadata(app, results)
    facts = [fact for result in results for fact in result.facts]
    validated_facts = _validate_facts(definitions, facts)
    dataset = build_prediction_dataset_from_validated_facts(
        home_team=home_team,
        away_team=away_team,
        validated_facts=validated_facts,
    )
    prediction = run_match_prediction(
        dataset,
        app.state.weight_registry.active_weight_version,
        simulation_count=simulation_count,
    )
    record = {
        "id": str(uuid4()),
        "home_team": prediction.home_team,
        "away_team": prediction.away_team,
        "weight_version": prediction.weight_version,
        "simulation_count": prediction.simulation_count,
        "expected_goals": prediction.expected_goals,
        "probabilities": prediction.probabilities,
        "top_scorelines": [
            {
                "home_goals": scoreline.home_goals,
                "away_goals": scoreline.away_goals,
                "probability": scoreline.probability,
            }
            for scoreline in prediction.top_scorelines
        ],
        "confidence_level": prediction.confidence_level,
        "dataset": {
            "home_team": dataset.home_team,
            "away_team": dataset.away_team,
            "home": {
                "attack_index": dataset.home.attack_index,
                "defense_weakness": dataset.home.defense_weakness,
            },
            "away": {
                "attack_index": dataset.away.attack_index,
                "defense_weakness": dataset.away.defense_weakness,
            },
            "home_advantage": dataset.home_advantage,
            "conflict_count": dataset.conflict_count,
        },
        "source_summary": {
            "ingested_source_count": len(results),
            "snapshot_count": sum(1 for result in results if result.snapshot),
            "normalized_fact_count": len(facts),
            "validated_fact_count": len(validated_facts),
            "conflict_count": dataset.conflict_count,
        },
        "source_evidence": [_source_evidence(result) for result in results],
        "validated_facts": [_validated_fact_payload(fact) for fact in validated_facts],
    }
    prediction_id = app.state.prediction_repository.save(record)

    return {
        "prediction_id": prediction_id,
        "home_team": home_team,
        "away_team": away_team,
        "source_category": category,
        "simulation_count": simulation_count,
        **record["source_summary"],
    }


def _load_source_definitions(app, category: str | None = None) -> list[SourceDefinition]:
    config = load_source_catalog_config(Path(app.state.source_config_path))
    return [
        definition
        for definition in config.sources
        if category is None or definition.category.value == category
    ]


def _ingest_definitions(app, definitions: list[SourceDefinition]):
    return [
        ingest_source_safely(
            definition,
            snapshot_dir=Path(app.state.source_snapshot_dir),
            http_client=getattr(app.state, "source_http_client", None),
        )
        for definition in definitions
    ]


def _record_snapshot_metadata(app, results) -> None:
    for result in results:
        if result.snapshot is None:
            continue
        app.state.source_snapshot_repository.save(
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


def _validate_facts(
    definitions: list[SourceDefinition],
    facts: list[NormalizedFact],
):
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


def _source_results_summary(results) -> dict:
    return {
        "source_count": len(results),
        "snapshot_count": sum(1 for result in results if result.snapshot),
        "fact_count": sum(len(result.facts) for result in results),
        "match_count": sum(len(result.matches) for result in results),
        "failed_source_count": sum(
            1 for result in results if result.status.value == "failed"
        ),
    }


def _source_evidence(result) -> dict:
    return {
        "source_name": result.source_name,
        "category": result.category.value if result.category else None,
        "status": result.status.value,
        "snapshot_path": str(result.snapshot.path) if result.snapshot else None,
        "content_hash": result.snapshot.content_hash if result.snapshot else None,
        "item_count": result.item_count,
        "fact_count": len(result.facts),
        "match_count": len(result.matches),
        "message": result.message,
    }


def _validated_fact_payload(fact: ValidatedFact) -> dict:
    return {
        "fact_type": fact.fact_type,
        "entity_key": fact.entity_key,
        "status": fact.status.value,
        "value": fact.value,
        "sources": fact.sources,
        "conflicting_values": {
            str(value): sources for value, sources in fact.conflicting_values.items()
        },
    }
