from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.data_sources import (
    EspnScoreboardDataSourceAdapter,
    EspnTeamScheduleDiscoveryDataSourceAdapter,
    HttpWebpageDataSourceAdapter,
    SportsMoleInjuryDataSourceAdapter,
    SourceIngestionResult,
    SourceIngestionStatus,
    WorldFootballEloDataSourceAdapter,
)
from app.source_config import SourceDefinition


def ingest_source(
    definition: SourceDefinition,
    *,
    snapshot_dir: Path,
    http_client=None,
) -> SourceIngestionResult:
    if definition.adapter == "espn_scoreboard":
        result = EspnScoreboardDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_schedule()
        return replace(result, category=definition.category)

    if definition.adapter == "espn_team_schedules":
        result = EspnTeamScheduleDiscoveryDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_team_form()
        return replace(result, category=definition.category)

    if definition.adapter == "webpage":
        result = HttpWebpageDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_snapshot()
        return replace(result, category=definition.category)

    if definition.adapter == "sportsmole_injuries":
        result = SportsMoleInjuryDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_injuries()
        return replace(result, category=definition.category)

    if definition.adapter == "world_football_elo":
        result = WorldFootballEloDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_rankings()
        return replace(result, category=definition.category)

    return SourceIngestionResult(
        source_name=definition.name,
        category=definition.category,
        status=SourceIngestionStatus.UNSUPPORTED,
        item_count=0,
        message=f"Adapter is not implemented yet: {definition.adapter}",
    )


def ingest_source_safely(
    definition: SourceDefinition,
    *,
    snapshot_dir: Path,
    http_client=None,
) -> SourceIngestionResult:
    try:
        return ingest_source(
            definition,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        )
    except Exception as error:
        return SourceIngestionResult(
            source_name=definition.name,
            category=definition.category,
            status=SourceIngestionStatus.FAILED,
            item_count=0,
            message=str(error),
        )
