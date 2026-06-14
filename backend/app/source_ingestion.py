from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.data_sources import (
    BetExplorerOddsDataSourceAdapter,
    EspnScoreboardDataSourceAdapter,
    EspnTeamRosterDiscoveryDataSourceAdapter,
    EspnTeamScheduleDiscoveryDataSourceAdapter,
    FifaRankingDataSourceAdapter,
    HttpWebpageDataSourceAdapter,
    OddsCheckerOddsDataSourceAdapter,
    SchemaOrgScheduleDataSourceAdapter,
    SportsMoleInjuryDataSourceAdapter,
    SourceIngestionResult,
    SourceIngestionStatus,
    TransfermarktInjuryDataSourceAdapter,
    TransfermarktSquadDataSourceAdapter,
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

    if definition.adapter == "espn_team_rosters":
        result = EspnTeamRosterDiscoveryDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_players()
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

    if definition.adapter == "fifa_ranking":
        result = FifaRankingDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_rankings()
        return replace(result, category=definition.category)

    if definition.adapter == "schema_org_schedule":
        result = SchemaOrgScheduleDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_schedule()
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

    if definition.adapter == "transfermarkt_injuries":
        result = TransfermarktInjuryDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_injuries()
        return replace(result, category=definition.category)

    if definition.adapter == "oddschecker_odds":
        result = OddsCheckerOddsDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_odds()
        return replace(result, category=definition.category)

    if definition.adapter == "betexplorer_odds":
        result = BetExplorerOddsDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_odds()
        return replace(result, category=definition.category)

    if definition.adapter == "transfermarkt_squads":
        result = TransfermarktSquadDataSourceAdapter(
            source_name=definition.name,
            url=definition.url,
            category=definition.category,
            snapshot_dir=snapshot_dir,
            http_client=http_client,
        ).ingest_players()
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
