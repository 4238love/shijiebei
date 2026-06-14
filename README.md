# World Cup Prediction Tool

DeepSeek/GPT assisted football prediction system. The Prediction Engine owns probabilities; AI providers generate analysis reports and reviewed weight recommendations only.

## Local startup

```powershell
docker compose up -d --build
```

Services:

- Frontend: <http://localhost:13000>
- Source operations page: <http://localhost:13000/sources>
- Methodology page: <http://localhost:13000/methodology>
- Backend health: <http://localhost:8000/health>
- Source catalog API: <http://localhost:8000/sources>
- PostgreSQL: `localhost:15432`

Docker Compose runs the backend with PostgreSQL-backed repositories for Match
Predictions, Backtest Runs, Weight Recommendations, and the active Weight
Version, AI Analysis Reports, and Source Snapshot metadata, so created records
survive backend container restarts.

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

The frontend Sources page includes an operations console for running snapshot-backed `ingest` or `validate` against all first-wave categories or one selected category:

- `Run ingest`: fetches configured sources and extracts matches/facts.
- `Run validate`: fetches configured sources, normalizes facts, and cross-checks them by source priority.
- Recent Source Snapshot metadata is available in the same page and through `GET /sources/snapshots`.

Webpage sources now return category-aware normalized facts when the static HTML contains extractable signals:

- `injury_availability`
- `decimal_odds`
- `news_sentiment`
- `player_presence`

Run a category validation pass to ingest all matching sources and cross-check facts by source priority:

```powershell
$body = @{ category = "injury" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/sources/validate -ContentType "application/json" -Body $body
```

Create a source-backed prediction by validating configured sources, constructing a Prediction Dataset, and then running the Prediction Engine:

```powershell
$body = @{
  home_team = "Brazil"
  away_team = "Croatia"
  simulation_count = 10000
  seed = 20260614
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/predictions/from-sources -ContentType "application/json" -Body $body
```

FIFA, Transfermarkt, OddsPortal, OddsChecker, BBC, and Elo pages are configured as crawl targets; their HTML/dynamic parsers should be added as separate adapters instead of being called directly from the prediction button.
