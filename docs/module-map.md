# Module Map

This map summarizes the current implementation using the project glossary.

## Runtime shape

- `docker-compose.yml` defines the Docker Compose web system: `frontend`, `backend`, and `postgres`.
- `backend/app/main.py` creates the FastAPI app and mounts public API seams.
- `frontend/app/page.tsx` renders the health and demo Match Prediction path.
- `frontend/app/methodology/page.tsx` renders the technical methodology page.

## Prediction path

- `backend/app/prediction_engine.py`
  - Owns `PredictionDataset`, `WeightVersion`, `MatchPrediction`, and Monte Carlo Simulation.
  - Produces win/draw/loss probabilities, top scorelines, expected goals, and Confidence Level.

- `backend/app/prediction_api.py`
  - Exposes `POST /predictions` and `GET /predictions/{id}`.

- `backend/app/prediction_repository.py`
  - Owns the Prediction Repository seam used by `prediction_api.py`.
  - Provides `InMemoryPredictionRepository` for tests/local seams and `PostgresPredictionRepository` for Docker deployment.

## Data source path

- `backend/app/data_sources.py`
  - Owns `FixtureDataSourceAdapter`, `HttpJsonDataSourceAdapter`, `SourceSnapshot`, and `SourceCatalog`.
  - Converts fixture or HTTP JSON source material into a Prediction Dataset.
  - `config/sources.example.json` records first-wave source categories and placeholder URLs.

- `backend/app/cross_source_validation.py`
  - Owns `NormalizedFact`, `ValidatedFact`, `ConflictStatus`, and `CrossSourceValidator`.
  - Applies Source Priority and emits confirmed, conflicting, missing, or stale facts.

## AI and weight path

- `backend/app/ai_reports.py`
  - Owns AI Analysis Report generation.
  - DeepSeek/GPT provider adapters receive structured copies of prediction data and cannot mutate probabilities or active weights.

- `backend/app/weights.py`
  - Owns Weight Recommendation and Weight Version review flow.
  - Recommendations remain inactive until reviewed with a backtest reference.

## Evidence path

- `backend/app/backtesting.py`
  - Owns Backtest Run metrics: outcome hit rate, Brier Score, Log Loss, scoreline Top-N hit rate, and conflict-status segmentation.

- `backend/app/scheduler_jobs.py`
  - Owns scheduled job registration for ingestion, prediction creation, and result collection.

## Current deepest seams

- Prediction Engine seam: tested through `run_match_prediction`.
- Data Source Adapter seam: tested through fixtures and injected HTTP clients.
- Cross-Source Validation seam: tested with normalized facts and source priority.
- AI Analysis Report seam: tested with fake providers.
- Backtest Run seam: tested with saved Match Predictions and actual results.

## Known next deepening opportunity

`PostgresPredictionRepository` persists the serialized Match Prediction payload. Future Backtest Runs need richer query seams for Prediction Dataset references, Weight Version references, and actual results instead of treating the payload as an opaque document.
