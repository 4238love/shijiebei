from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ConflictStatus(StrEnum):
    CONFIRMED = "confirmed"
    CONFLICTING = "conflicting"
    MISSING = "missing"
    STALE = "stale"


@dataclass(frozen=True)
class NormalizedFact:
    fact_type: str
    entity_key: str
    value: Any
    source_name: str
    is_stale: bool = False


@dataclass(frozen=True)
class ValidatedFact:
    fact_type: str
    entity_key: str
    status: ConflictStatus
    value: Any | None
    sources: list[str]
    conflicting_values: dict[Any, list[str]]


class CrossSourceValidator:
    def __init__(self, *, source_priority: dict[str, list[str]]):
        self.source_priority = source_priority

    def validate(
        self,
        *,
        fact_type: str,
        entity_key: str,
        facts: list[NormalizedFact],
    ) -> ValidatedFact:
        relevant_facts = [
            fact
            for fact in facts
            if fact.fact_type == fact_type and fact.entity_key == entity_key
        ]

        if not relevant_facts:
            return self._result(fact_type, entity_key, ConflictStatus.MISSING)

        fresh_facts = [fact for fact in relevant_facts if not fact.is_stale]
        if not fresh_facts:
            return self._result(
                fact_type,
                entity_key,
                ConflictStatus.STALE,
                sources=self._ordered_sources(relevant_facts, fact_type),
            )

        values = defaultdict(list)
        for fact in fresh_facts:
            values[fact.value].append(fact.source_name)

        conflicting_values = {
            value: self._ordered_source_names(source_names, fact_type)
            for value, source_names in values.items()
        }

        if len(conflicting_values) == 1:
            value = next(iter(conflicting_values))
            return self._result(
                fact_type,
                entity_key,
                ConflictStatus.CONFIRMED,
                value=value,
                sources=self._ordered_sources(fresh_facts, fact_type),
            )

        selected_value = self._highest_priority_fact(fresh_facts, fact_type).value
        return self._result(
            fact_type,
            entity_key,
            ConflictStatus.CONFLICTING,
            value=selected_value,
            sources=self._ordered_sources(fresh_facts, fact_type),
            conflicting_values=conflicting_values,
        )

    def _result(
        self,
        fact_type: str,
        entity_key: str,
        status: ConflictStatus,
        *,
        value: Any | None = None,
        sources: list[str] | None = None,
        conflicting_values: dict[Any, list[str]] | None = None,
    ) -> ValidatedFact:
        return ValidatedFact(
            fact_type=fact_type,
            entity_key=entity_key,
            status=status,
            value=value,
            sources=sources or [],
            conflicting_values=conflicting_values or {},
        )

    def _highest_priority_fact(
        self,
        facts: list[NormalizedFact],
        fact_type: str,
    ) -> NormalizedFact:
        return sorted(facts, key=lambda fact: self._source_rank(fact.source_name, fact_type))[0]

    def _ordered_sources(self, facts: list[NormalizedFact], fact_type: str) -> list[str]:
        return self._ordered_source_names(
            list({fact.source_name for fact in facts}),
            fact_type,
        )

    def _ordered_source_names(self, source_names: list[str], fact_type: str) -> list[str]:
        return sorted(source_names, key=lambda source_name: self._source_rank(source_name, fact_type))

    def _source_rank(self, source_name: str, fact_type: str) -> tuple[int, str]:
        priority = self.source_priority.get(fact_type, [])
        try:
            return (priority.index(source_name), source_name)
        except ValueError:
            return (len(priority), source_name)


def confidence_penalty(status: ConflictStatus) -> int:
    return {
        ConflictStatus.CONFIRMED: 0,
        ConflictStatus.MISSING: 1,
        ConflictStatus.STALE: 1,
        ConflictStatus.CONFLICTING: 2,
    }[status]
