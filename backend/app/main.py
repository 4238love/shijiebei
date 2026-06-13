from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.health import router as health_router
from app.methodology_api import router as methodology_router
from app.prediction_api import router as prediction_router
from app.prediction_repository import PredictionRepository, default_prediction_repository


def create_app(prediction_repository: PredictionRepository | None = None) -> FastAPI:
    app = FastAPI(title="World Cup Prediction Tool API")
    app.state.prediction_repository = prediction_repository or default_prediction_repository()

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
    return app


app = create_app()
