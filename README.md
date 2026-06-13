# World Cup Prediction Tool

DeepSeek/GPT assisted football prediction system. The Prediction Engine owns probabilities; AI providers generate analysis reports and reviewed weight recommendations only.

## Local startup

```powershell
docker compose up -d --build
```

Services:

- Frontend: <http://localhost:3000>
- Backend health: <http://localhost:8000/health>
- PostgreSQL: `localhost:5432`

## Development checks

```powershell
python -m pytest
```

The first vertical slice verifies the Docker Compose service shape and the backend health path.

## Data sources

Copy `config/sources.example.json` to `config/sources.local.json` and replace the placeholder URLs with the real websites or API endpoints selected for the first live crawl. Each category is isolated behind a Data Source Adapter and writes Source Snapshots before normalization.
