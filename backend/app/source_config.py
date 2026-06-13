from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from app.data_sources import SourceCatalog, SourceCategory


@dataclass(frozen=True)
class SourceDefinition:
    category: SourceCategory
    name: str
    url: str
    priority: int
    adapter: str
    notes: str = ""


@dataclass(frozen=True)
class SourceCatalogConfig:
    sources: list[SourceDefinition]
    catalog: SourceCatalog


def load_source_catalog_config(path: Path) -> SourceCatalogConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    sources: list[SourceDefinition] = []
    sources_by_category: dict[SourceCategory, list[str]] = {}

    for category_value, entries in raw.items():
        category = SourceCategory(category_value)
        for entry in entries:
            source = SourceDefinition(
                category=category,
                name=entry["name"],
                url=entry["url"],
                priority=int(entry.get("priority", 1)),
                adapter=entry.get("adapter", "webpage"),
                notes=entry.get("notes", ""),
            )
            sources.append(source)
            sources_by_category.setdefault(category, []).append(source.name)

    return SourceCatalogConfig(
        sources=sources,
        catalog=SourceCatalog(sources_by_category),
    )
