from pathlib import Path

from app.source_config import load_source_catalog_config


def test_local_source_config_has_all_first_wave_categories():
    config = load_source_catalog_config(Path("config/sources.local.json"))

    assert config.catalog.missing_first_wave_categories() == []


def test_local_source_config_uses_real_urls_not_placeholders():
    config = load_source_catalog_config(Path("config/sources.local.json"))

    for source in config.sources:
        assert source.url.startswith("https://")
        assert "example" not in source.url
        assert source.name
        assert source.priority >= 1


def test_local_source_config_includes_committed_cross_check_websites():
    config = load_source_catalog_config(Path("config/sources.local.json"))
    urls = " ".join(source.url for source in config.sources)

    for hostname in [
        "fifa.com",
        "transfermarkt.com",
        "oddsportal.com",
        "oddschecker.com",
        "bbc.com",
        "eloratings.net",
    ]:
        assert hostname in urls


def test_local_source_config_uses_dedicated_transfermarkt_injury_adapter():
    config = load_source_catalog_config(Path("config/sources.local.json"))

    transfermarkt_injury_sources = [
        source
        for source in config.sources
        if source.name == "transfermarkt-world-cup-2026-injuries"
    ]

    assert len(transfermarkt_injury_sources) == 1
    assert transfermarkt_injury_sources[0].adapter == "transfermarkt_injuries"


def test_local_source_config_uses_dedicated_oddschecker_odds_adapter():
    config = load_source_catalog_config(Path("config/sources.local.json"))

    oddschecker_sources = [
        source for source in config.sources if source.name == "oddschecker-world-cup"
    ]

    assert len(oddschecker_sources) == 1
    assert oddschecker_sources[0].adapter == "oddschecker_odds"


def test_local_source_config_uses_dedicated_betexplorer_odds_adapter():
    config = load_source_catalog_config(Path("config/sources.local.json"))

    betexplorer_sources = [
        source for source in config.sources if source.name == "betexplorer-world-cup"
    ]

    assert len(betexplorer_sources) == 1
    assert betexplorer_sources[0].adapter == "betexplorer_odds"


def test_local_source_config_uses_dedicated_transfermarkt_squad_adapter():
    config = load_source_catalog_config(Path("config/sources.local.json"))

    transfermarkt_squad_sources = [
        source
        for source in config.sources
        if source.name == "transfermarkt-world-cup-2026-squads"
    ]

    assert len(transfermarkt_squad_sources) == 1
    assert transfermarkt_squad_sources[0].adapter == "transfermarkt_squads"


def test_local_source_config_uses_dedicated_fifa_ranking_adapter():
    config = load_source_catalog_config(Path("config/sources.local.json"))

    fifa_ranking_sources = [
        source for source in config.sources if source.name == "fifa-men-ranking"
    ]

    assert len(fifa_ranking_sources) == 1
    assert fifa_ranking_sources[0].adapter == "fifa_ranking"


def test_local_source_config_uses_dedicated_schema_org_schedule_adapter():
    config = load_source_catalog_config(Path("config/sources.local.json"))

    schedule_sources = [
        source
        for source in config.sources
        if source.name in {"fifa-2026-fixtures", "oddsportal-world-cup-schedule"}
    ]

    assert len(schedule_sources) == 2
    assert {source.adapter for source in schedule_sources} == {"schema_org_schedule"}


def test_local_source_config_uses_dedicated_news_sentiment_adapter():
    config = load_source_catalog_config(Path("config/sources.local.json"))

    news_sources = [
        source
        for source in config.sources
        if source.name in {"bbc-world-cup-football", "fifa-world-cup-news"}
    ]

    assert len(news_sources) == 2
    assert {source.adapter for source in news_sources} == {"news_sentiment"}


def test_local_source_config_uses_dedicated_injury_news_adapter():
    config = load_source_catalog_config(Path("config/sources.local.json"))

    injury_news_sources = [
        source
        for source in config.sources
        if source.name
        in {"bbc-world-cup-football-injuries", "fifa-world-cup-news-injuries"}
    ]

    assert len(injury_news_sources) == 2
    assert {source.adapter for source in injury_news_sources} == {"injury_news"}
