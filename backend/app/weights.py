from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from app.prediction_engine import WeightVersion

SUPPORTED_WEIGHT_RECOMMENDATION_PROVIDERS = {"deepseek", "gpt"}


class WeightRecommendationStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class WeightRecommendation:
    id: str
    provider_name: str
    proposed_factors: dict[str, float]
    rationale: str
    status: WeightRecommendationStatus
    reviewer: str | None = None
    backtest_reference: str | None = None
    activated_version_name: str | None = None


class WeightRecommendationRepository(Protocol):
    def save_recommendation(self, recommendation: WeightRecommendation) -> None:
        ...

    def get_recommendation(
        self, recommendation_id: str
    ) -> WeightRecommendation | None:
        ...

    def save_active_weight_version(self, weight_version: WeightVersion) -> None:
        ...

    def get_active_weight_version(self) -> WeightVersion | None:
        ...


class WeightRecommendationRegistry:
    def __init__(
        self,
        *,
        active_weight_version: WeightVersion,
        repository: WeightRecommendationRepository | None = None,
    ):
        self._repository = repository
        stored_active = (
            repository.get_active_weight_version() if repository is not None else None
        )
        self.active_weight_version = stored_active or active_weight_version
        self._recommendations: dict[str, WeightRecommendation] = {}
        if repository is not None and stored_active is None:
            repository.save_active_weight_version(active_weight_version)

    def create_recommendation(
        self,
        *,
        provider_name: str,
        proposed_factors: dict[str, float],
        rationale: str,
    ) -> WeightRecommendation:
        if provider_name not in SUPPORTED_WEIGHT_RECOMMENDATION_PROVIDERS:
            raise ValueError("Only deepseek and gpt providers are supported")

        recommendation = WeightRecommendation(
            id=str(uuid4()),
            provider_name=provider_name,
            proposed_factors=dict(proposed_factors),
            rationale=rationale,
            status=WeightRecommendationStatus.PROPOSED,
        )
        self._recommendations[recommendation.id] = recommendation
        if self._repository is not None:
            self._repository.save_recommendation(recommendation)
        return recommendation

    def approve_recommendation(
        self,
        *,
        recommendation_id: str,
        reviewer: str,
        backtest_reference: str,
        new_version_name: str,
    ) -> WeightVersion:
        if not backtest_reference:
            raise ValueError("backtest_reference is required")

        recommendation = self.get_recommendation(recommendation_id)
        factors = {
            **self.active_weight_version.factors,
            **recommendation.proposed_factors,
        }
        activated = WeightVersion(name=new_version_name, factors=factors)
        approved = replace(
            recommendation,
            status=WeightRecommendationStatus.APPROVED,
            reviewer=reviewer,
            backtest_reference=backtest_reference,
            activated_version_name=new_version_name,
        )
        self._recommendations[recommendation_id] = approved
        self.active_weight_version = activated
        if self._repository is not None:
            self._repository.save_recommendation(approved)
            self._repository.save_active_weight_version(activated)
        return activated

    def get_recommendation(self, recommendation_id: str) -> WeightRecommendation:
        cached = self._recommendations.get(recommendation_id)
        if cached is not None:
            return cached

        stored = (
            self._repository.get_recommendation(recommendation_id)
            if self._repository is not None
            else None
        )
        if stored is not None:
            self._recommendations[recommendation_id] = stored
            return stored

        raise KeyError(f"Unknown weight recommendation: {recommendation_id}")
