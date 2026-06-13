from app.ai_reports import (
    AIProviderConfig,
    generate_ai_analysis_report,
)
from app.cross_source_validation import ConflictStatus, ValidatedFact
from app.prediction_engine import (
    MatchPrediction,
    ScorelineProbability,
)


class FakeProvider:
    provider_name = "fake-deepseek"
    model_name = "fake-chat"

    def __init__(self):
        self.payload = None

    def generate_report(self, payload):
        self.payload = payload
        return "Brazil has the stronger statistical profile, but draw risk remains visible."


class MutatingProvider(FakeProvider):
    def generate_report(self, payload):
        payload["probabilities"]["home_win"] = 0.0
        payload["weight_version"] = "mutated"
        return "Attempted mutation."


def sample_prediction() -> MatchPrediction:
    return MatchPrediction(
        home_team="Brazil",
        away_team="Croatia",
        weight_version="baseline",
        simulation_count=10_000,
        expected_goals={"home": 1.85, "away": 0.95},
        probabilities={"home_win": 0.58, "draw": 0.24, "away_win": 0.18},
        top_scorelines=(
            ScorelineProbability(1, 0, 0.12),
            ScorelineProbability(2, 0, 0.1),
        ),
        confidence_level="A",
    )


def test_report_uses_structured_prediction_and_conflict_statuses():
    provider = FakeProvider()
    validated_facts = [
        ValidatedFact(
            fact_type="injury",
            entity_key="Brazil:Neymar",
            status=ConflictStatus.CONFLICTING,
            value="available",
            sources=["official", "news"],
            conflicting_values={"available": ["official"], "doubtful": ["news"]},
        )
    ]

    report = generate_ai_analysis_report(
        prediction=sample_prediction(),
        provider=provider,
        validated_facts=validated_facts,
    )

    assert report.provider_name == "fake-deepseek"
    assert report.model_name == "fake-chat"
    assert "stronger statistical profile" in report.content
    assert provider.payload["match"] == "Brazil vs Croatia"
    assert provider.payload["probabilities"]["home_win"] == 0.58
    assert provider.payload["conflict_statuses"][0]["status"] == "conflicting"


def test_provider_payload_mutation_cannot_change_match_prediction():
    prediction = sample_prediction()

    report = generate_ai_analysis_report(
        prediction=prediction,
        provider=MutatingProvider(),
        validated_facts=[],
    )

    assert report.content == "Attempted mutation."
    assert prediction.probabilities["home_win"] == 0.58
    assert prediction.weight_version == "baseline"


def test_deepseek_and_gpt_configs_are_separate():
    deepseek = AIProviderConfig.deepseek()
    gpt = AIProviderConfig.gpt()

    assert deepseek.provider_name == "deepseek"
    assert deepseek.api_key_env == "DEEPSEEK_API_KEY"
    assert gpt.provider_name == "gpt"
    assert gpt.api_key_env == "OPENAI_API_KEY"
    assert deepseek.model_name != gpt.model_name
