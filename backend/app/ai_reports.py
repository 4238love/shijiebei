from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.cross_source_validation import ValidatedFact
from app.prediction_engine import MatchPrediction


class AIReportProvider(Protocol):
    provider_name: str
    model_name: str

    def generate_report(self, payload: dict) -> str:
        ...


@dataclass(frozen=True)
class AIProviderConfig:
    provider_name: str
    model_name: str
    api_key_env: str
    base_url: str

    @classmethod
    def deepseek(cls) -> AIProviderConfig:
        return cls(
            provider_name="deepseek",
            model_name="deepseek-chat",
            api_key_env="DEEPSEEK_API_KEY",
            base_url="https://api.deepseek.com",
        )

    @classmethod
    def gpt(cls) -> AIProviderConfig:
        return cls(
            provider_name="gpt",
            model_name="gpt-5.2",
            api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
        )


@dataclass(frozen=True)
class AIAnalysisReport:
    provider_name: str
    model_name: str
    content: str
    input_summary: dict


def generate_ai_analysis_report(
    *,
    prediction: MatchPrediction,
    provider: AIReportProvider,
    validated_facts: list[ValidatedFact],
) -> AIAnalysisReport:
    payload = _report_payload(prediction, validated_facts)
    content = provider.generate_report(payload)

    return AIAnalysisReport(
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        content=content,
        input_summary=payload,
    )


def _report_payload(
    prediction: MatchPrediction,
    validated_facts: list[ValidatedFact],
) -> dict:
    return {
        "match": f"{prediction.home_team} vs {prediction.away_team}",
        "home_team": prediction.home_team,
        "away_team": prediction.away_team,
        "weight_version": prediction.weight_version,
        "simulation_count": prediction.simulation_count,
        "expected_goals": dict(prediction.expected_goals),
        "probabilities": dict(prediction.probabilities),
        "top_scorelines": [
            {
                "home_goals": scoreline.home_goals,
                "away_goals": scoreline.away_goals,
                "probability": scoreline.probability,
            }
            for scoreline in prediction.top_scorelines
        ],
        "confidence_level": prediction.confidence_level,
        "conflict_statuses": [
            {
                "fact_type": fact.fact_type,
                "entity_key": fact.entity_key,
                "status": fact.status.value,
                "value": fact.value,
                "sources": list(fact.sources),
                "conflicting_values": {
                    str(value): list(sources)
                    for value, sources in fact.conflicting_values.items()
                },
            }
            for fact in validated_facts
        ],
    }
