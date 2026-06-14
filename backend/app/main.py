from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai_report_api import router as ai_report_router
from app.backtest_api import router as backtest_router
from app.backtest_repository import BacktestRepository, default_backtest_repository
from app.health import router as health_router
from app.methodology_api import router as methodology_router
from app.prediction_api import router as prediction_router
from app.prediction_repository import PredictionRepository, default_prediction_repository
from app.source_api import router as source_router
from app.weight_api import create_weight_registry, router as weight_router


def _default_source_config_path() -> Path:
    local_config = Path("config/sources.local.json")
    if local_config.exists():
        return local_config

    return Path("config/sources.example.json")


def create_app(
    prediction_repository: PredictionRepository | None = None,
    backtest_repository: BacktestRepository | None = None,
    *,
    source_config_path: Path | None = None,
    source_snapshot_dir: Path | None = None,
    source_http_client=None,
) -> FastAPI:
    app = FastAPI(title="World Cup Prediction Tool API")
    app.state.prediction_repository = prediction_repository or default_prediction_repository()
    app.state.backtest_repository = backtest_repository or default_backtest_repository()
    app.state.source_config_path = source_config_path or _default_source_config_path()
    app.state.source_snapshot_dir = source_snapshot_dir or Path(".scratch/source-snapshots")
    app.state.source_http_client = source_http_client
    app.state.weight_registry = create_weight_registry()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(prediction_router)
    app.include_router(methodology_router)
    app.include_router(source_router)
    app.include_router(backtest_router)
    app.include_router(weight_router)
    app.include_router(ai_report_router)
    return app


app = create_app()
