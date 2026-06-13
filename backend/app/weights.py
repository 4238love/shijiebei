from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import uuid4

from app.prediction_engine import WeightVersion


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


class WeightRecommendationRegistry:
    def __init__(self, *, active_weight_version: WeightVersion):
        self.active_weight_version = active_weight_version
        self._recommendations: dict[str, WeightRecommendation] = {}

    def create_recommendation(
        self,
        *,
        provider_name: str,
        proposed_factors: dict[str, float],
        rationale: str,
    ) -> WeightRecommendation:
        recommendation = WeightRecommendation(
            id=str(uuid4()),
            provider_name=provider_name,
            proposed_factors=dict(proposed_factors),
            rationale=rationale,
            status=WeightRecommendationStatus.PROPOSED,
        )
        self._recommendations[recommendation.id] = recommendation
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
        return activated

    def get_recommendation(self, recommendation_id: str) -> WeightRecommendation:
        try:
            return self._recommendations[recommendation_id]
        except KeyError as error:
            raise KeyError(f"Unknown weight recommendation: {recommendation_id}") from error
