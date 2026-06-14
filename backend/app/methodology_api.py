from fastapi import APIRouter

router = APIRouter(tags=["methodology"])


@router.get("/methodology")
async def methodology():
    return {
        "prediction_engine": {
            "principle": "Prediction Engine owns probabilities; DeepSeek/GPT explain structured results.",
            "inputs": [
                "Prediction Dataset",
                "Weight Version",
                "Strategy Factors",
                "Conflict Status",
                "Market odds strength signal",
            ],
        },
        "monte_carlo": {
            "default_simulations": 10_000,
            "distribution": "Poisson scoreline simulation",
            "outputs": ["win/draw/loss probabilities", "top scorelines", "confidence level"],
        },
        "ai_analysis": {
            "providers": ["deepseek", "gpt"],
            "role": "Generate analysis reports and reviewed Weight Recommendations.",
            "can_change_probabilities": False,
            "can_auto_activate_weights": False,
        },
        "cross_source_validation": {
            "statuses": ["confirmed", "conflicting", "missing", "stale"],
            "principle": "Conflicts are shown and reduce Confidence Level instead of being silently merged.",
        },
        "source_backed_prediction": {
            "endpoint": "POST /predictions/from-sources",
            "principle": "Validated Facts are transformed into a Prediction Dataset before the Prediction Engine runs.",
            "outputs": [
                "Match Prediction",
                "Prediction Dataset",
                "source summary",
            ],
            "dataset_signals": [
                "team ratings",
                "team form",
                "market decimal odds",
                "team availability / unavailable player counts",
                "squad depth / listed player counts",
                "cross-source conflict penalties",
            ],
        },
        "backtest_run": {
            "metrics": [
                "outcome hit rate",
                "Brier Score",
                "Log Loss",
                "scoreline Top-N hit rate",
                "conflict-status segmentation",
            ]
        },
    }
