# World Cup Prediction Tool

DeepSeek/GPT assisted football prediction system. The Prediction Engine owns probabilities; AI providers generate analysis reports and reviewed weight recommendations only.

## Local startup

```powershell
docker compose up -d --build
```

Services:

- Frontend: <http://localhost:13000>
- Source catalog page: <http://localhost:13000/sources>
- Methodology page: <http://localhost:13000/methodology>
- Backend health: <http://localhost:8000/health>
- Source catalog API: <http://localhost:8000/sources>
- PostgreSQL: `localhost:15432`

## Development checks

```powershell
python -m pytest
```

The first vertical slice verifies the Docker Compose service shape and the backend health path.

## Data sources

`config/sources.local.json` contains the first real source catalog for:

- schedule
- team_form
- ranking
- injury
- odds
- news_sentiment
- player

Each category is isolated behind a Data Source Adapter and writes Source Snapshots before normalization. ESPN scoreboard is the first implemented live parser:

```powershell
$body = @{ category = "schedule"; source_name = "espn-world-cup-scoreboard" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/sources/ingest -ContentType "application/json" -Body $body
```

FIFA, Transfermarkt, OddsPortal, OddsChecker, BBC, and Elo pages are configured as crawl targets; their HTML/dynamic parsers should be added as separate adapters instead of being called directly from the prediction button.
