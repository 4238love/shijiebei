from __future__ import annotations

from dataclasses import dataclass
import json
import os
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


class UnknownAIReportProvider(ValueError):
    pass


class TemplateAIReportProvider:
    def __init__(self, config: AIProviderConfig):
        self.provider_name = config.provider_name
        self.model_name = config.model_name

    def generate_report(self, payload: dict) -> str:
        probabilities = payload["probabilities"]
        strongest_outcome = max(probabilities.items(), key=lambda item: item[1])[0]
        strongest_outcome_label = _outcome_label(strongest_outcome)
        return (
            f"{payload['match']} 的 AI 复核报告"
            f"（{self.provider_name}/{self.model_name}）："
            f"统计模型最强结果为{strongest_outcome_label}；"
            f"置信等级为 {payload['confidence_level']}；"
            f"已复核 {len(payload['conflict_statuses'])} 条数据源事实。"
            "本报告只解释预测依据，不会改写概率、权重或数据源事实。"
        )


class OpenAICompatibleAIReportProvider:
    def __init__(
        self,
        config: AIProviderConfig,
        *,
        api_key: str | None = None,
        http_client=None,
        timeout_seconds: int = 45,
    ):
        self.provider_name = config.provider_name
        self.model_name = config.model_name
        self.base_url = config.base_url.rstrip("/")
        self.api_key = api_key or os.getenv(config.api_key_env)
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def generate_report(self, payload: dict) -> str:
        if not self.api_key:
            raise RuntimeError(f"Missing API key for {self.provider_name}")

        response = self._http_client().post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model_name,
                "messages": _chat_completion_messages(payload),
                "temperature": 0.2,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return _chat_completion_content(response.json())

    def _http_client(self):
        if self.http_client is not None:
            return self.http_client

        import httpx

        return httpx


def provider_for_name(provider_name: str) -> AIReportProvider:
    if provider_name == "deepseek":
        config = AIProviderConfig.deepseek()
    elif provider_name == "gpt":
        config = AIProviderConfig.gpt()
    else:
        raise UnknownAIReportProvider(
            "Only deepseek and gpt providers are supported"
        )

    if os.getenv("AI_REPORT_MODE") == "live":
        return OpenAICompatibleAIReportProvider(config)

    return TemplateAIReportProvider(config)


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
        "language": "zh-CN",
        "language_instruction": (
            "所有面向用户的报告内容必须使用简体中文。"
            "球队名、胜平负、证据说明、冲突说明和建议都应中文表达。"
        ),
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


def _chat_completion_messages(payload: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是世界杯预测系统的中文分析员。"
                "必须只使用简体中文输出，不能夹杂英文段落或英文小标题；"
                "常见球队名也尽量使用中文译名。"
                "不要改写概率、预期进球、当前权重或数据源事实。"
                "请解释统计结果，引用关键数据源证据，指出冲突，"
                "并保持所有建议仅用于人工复核。"
                "输出控制在 4 到 6 个短段落，标题也使用中文。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请根据以下结构化数据生成简体中文 AI 报告。"
                "报告中不要出现英文标题如 Match Analysis、Statistical Summary、"
                "Key Source Evidence、Confidence Level。"
                "结构化数据：\n"
                f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
            ),
        },
    ]


def _chat_completion_content(response_payload: dict) -> str:
    choices = response_payload.get("choices", [])
    if not choices:
        return ""

    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict)
        )
    return str(content)


def _outcome_label(outcome: str) -> str:
    labels = {
        "away_win": "客胜",
        "draw": "平局",
        "home_win": "主胜",
    }
    return labels.get(outcome, outcome)
