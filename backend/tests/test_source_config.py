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
