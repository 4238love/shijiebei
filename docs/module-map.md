# Module Map

This map summarizes the current implementation using the project glossary.

## Runtime shape

- `docker-compose.yml` defines the Docker Compose web system: `frontend`, `backend`, and `postgres`.
- `backend/app/main.py` creates the FastAPI app and mounts public API seams.
- `frontend/app/page.tsx` renders health status and mounts the live prediction workbench.
- `frontend/app/source-backed-prediction-workbench.tsx` lets an operator pick teams/source scope and run source-backed predictions from the browser.
- `frontend/app/api/predictions/from-sources/route.ts` proxies browser requests to backend `POST /predictions/from-sources`.
- `frontend/app/predictions/page.tsx` renders saved prediction history from backend `GET /predictions`.
- `frontend/app/predictions/[id]/page.tsx` renders the saved Prediction Dataset, source summary, and Source Snapshot evidence for a single run.
- `frontend/app/jobs/page.tsx` and `frontend/app/jobs/jobs-dashboard.tsx` render the pipeline job control room.
- `frontend/app/api/jobs/` proxies job status and run requests from the browser to the backend.
- `frontend/app/methodology/page.tsx` renders the technical methodology page.

## Prediction path

- `backend/app/prediction_engine.py`
  - Owns `PredictionDataset`, `WeightVersion`, `MatchPrediction`, and Monte Carlo Simulation.
  - Produces win/draw/loss probabilities, top scorelines, expected goals, and Confidence Level.

- `backend/app/prediction_dataset_builder.py`
  - Builds a Prediction Dataset from Validated Facts emitted by source ingestion and cross-source validation.
  - Turns non-confirmed facts into the Conflict Status penalty used by Confidence Level.

- `backend/app/prediction_api.py`
  - Exposes `GET /predictions`, `POST /predictions`, `POST /predictions/from-sources`, `GET /predictions/{id}`, and `GET /predictions/{id}/record`.

- `backend/app/prediction_repository.py`
  - Owns the Prediction Repository seam used by `prediction_api.py`.
  - Provides `InMemoryPredictionRepository` for tests/local seams and `PostgresPredictionRepository` for Docker deployment.

## Data source path

- `backend/app/data_sources.py`
  - Owns `FixtureDataSourceAdapter`, `HttpJsonDataSourceAdapter`, `SourceSnapshot`, and `SourceCatalog`.
  - Converts fixture or HTTP JSON source material into a Prediction Dataset.
  - `config/sources.example.json` records first-wave source categories and placeholder URLs.

- `backend/app/source_snapshot_repository.py`
  - Owns Source Snapshot metadata persistence for snapshot path, content hash, category, status, and extracted fact/match counts.
  - Provides in-memory storage for tests/local seams and PostgreSQL storage for Docker deployment.

- `backend/app/cross_source_validation.py`
  - Owns `NormalizedFact`, `ValidatedFact`, `ConflictStatus`, and `CrossSourceValidator`.
  - Applies Source Priority and emits confirmed, conflicting, missing, or stale facts.

## AI and weight path

- `backend/app/ai_reports.py`
  - Owns AI Analysis Report generation.
  - DeepSeek/GPT provider adapters receive structured copies of prediction data and cannot mutate probabilities or active weights.

- `backend/app/ai_report_repository.py`
  - Owns the AI Analysis Report repository seam.
  - Provides in-memory storage for tests/local seams and PostgreSQL storage for Docker deployment.

- `backend/app/weights.py`
  - Owns Weight Recommendation and Weight Version review flow.
  - Recommendations remain inactive until reviewed with a backtest reference.

- `backend/app/weight_repository.py`
  - Owns the Weight Recommendation and active Weight Version repository seam.
  - Provides in-memory storage for tests/local seams and PostgreSQL storage for Docker deployment.

## Evidence path

- `backend/app/backtesting.py`
  - Owns Backtest Run metrics: outcome hit rate, Brier Score, Log Loss, scoreline Top-N hit rate, and conflict-status segmentation.

- `backend/app/backtest_repository.py`
  - Owns the Backtest Repository seam used by `backtest_api.py`.
  - Provides `InMemoryBacktestRepository` for tests/local seams and `PostgresBacktestRepository` for Docker deployment.

- `backend/app/scheduler_jobs.py`
  - Owns scheduled job registration for ingestion, prediction creation, and result collection.

- `backend/app/job_runner.py` and `backend/app/job_api.py`
  - Own in-process pipeline job state and expose `GET /jobs` plus `POST /jobs/{job_id}/run`.
  - Registered jobs cover source ingestion, source validation, and source-backed prediction creation.

## Current deepest seams

- Prediction Engine seam: tested through `run_match_prediction`.
- Source-backed Prediction Dataset seam: tested through `build_prediction_dataset_from_validated_facts`.
- Data Source Adapter seam: tested through fixtures and injected HTTP clients.
- Cross-Source Validation seam: tested with normalized facts and source priority.
- AI Analysis Report seam: tested with fake providers.
- Backtest Run seam: tested with saved Match Predictions and actual results.

## Known next deepening opportunity

`PostgresPredictionRepository`, `PostgresBacktestRepository`, `PostgresWeightRepository`, `PostgresAIReportRepository`, and `PostgresSourceSnapshotRepository` persist serialized API payloads or snapshot metadata. Future deepening should add richer query seams for Prediction Dataset references, Weight Version lineage, report provenance, and actual results instead of treating those records as opaque documents.
