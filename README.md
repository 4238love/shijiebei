# World Cup Prediction Tool

DeepSeek/GPT assisted football prediction system. The Prediction Engine owns probabilities; AI providers generate analysis reports and reviewed weight recommendations only.

AI reports default to deterministic template mode for local development. Set
`AI_REPORT_MODE=live` plus `OPENAI_API_KEY` and/or `DEEPSEEK_API_KEY` to call
OpenAI-compatible Chat Completions endpoints for GPT or DeepSeek reports. Live
providers receive structured prediction/source evidence and cannot mutate saved
probabilities or active weights.

## Local startup

```powershell
docker compose up -d --build
```

Services:

- Frontend: <http://localhost:13000>
- Live source-backed prediction workbench: <http://localhost:13000>
- Prediction history and evidence detail: <http://localhost:13000/predictions>
- Pipeline jobs console: <http://localhost:13000/jobs>
- Source operations page: <http://localhost:13000/sources>
- Methodology page: <http://localhost:13000/methodology>
- Backend health: <http://localhost:8000/health>
- Source catalog API: <http://localhost:8000/sources>
- PostgreSQL: `localhost:15432`

Docker Compose runs the backend with PostgreSQL-backed repositories for Match
Predictions, Backtest Runs, Weight Recommendations, and the active Weight
Version, AI Analysis Reports, Source Snapshot metadata, and Pipeline Job Runs,
so created records survive backend container restarts.

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

Configured source adapters now return category-aware normalized facts when
snapshots contain extractable signals:

- `fixture_kickoff`
- `injury_availability`
- `team_unavailable_player_count`
- `decimal_odds`
- `news_sentiment`
- `team_news_sentiment`
- `player_presence`
- `team_listed_player_count`
- `team_presence`

World Football Elo uses a dedicated adapter that snapshots `World.tsv` plus
`en.teams.tsv`, maps country codes to team names, and emits `team_rating` /
`team_ranking_position` facts. The same adapter is also used for the Elo
team-form context source so both Elo entries are fetched through stable TSV
endpoints rather than generic page scraping.
FIFA ranking uses a dedicated adapter for the official men's ranking page; it
extracts embedded ranking JSON when present and falls back to static page text
for `team_rating` / `team_ranking_position` facts.

ESPN team schedule endpoints can be configured as `team_form` sources. The
scoreboard adapter accepts both string scores and ESPN score objects, then keeps
the latest completed match per team so recent-form facts do not self-conflict.
The `espn_team_schedules` adapter can start from ESPN's team index, discover team
IDs, fetch each team schedule, and emit the same recent-form facts without
manually listing one URL per team.
ESPN discovery adapters reuse a fresh JSON snapshot for 15 minutes so repeated
validation/prediction runs do not re-fetch every team endpoint.

Schedule sources can use the dedicated `schema_org_schedule` adapter to parse
Schema.org `SportsEvent` JSON-LD blocks into `fixture_kickoff` facts.
`config/sources.local.json` uses this for FIFA and OddsPortal schedule
fallbacks so ESPN schedule facts can be cross-checked against additional
websites when static event metadata is available.

Sports Mole injury sources use a dedicated crawler: the adapter snapshots the
World Cup injury index, follows article links, then parses team
`Out`/`Doubtful`/`Suspended` sections into `injury_availability` and
`team_unavailable_player_count` facts.
`config/sources.local.json` also includes Transfermarkt as a secondary injury
target using the dedicated `transfermarkt_injuries` adapter, so availability
signals can be checked against Sports Mole, BBC, and FIFA news pages.
BBC/FIFA injury-news fallbacks use the dedicated `injury_news` adapter, which
extracts Schema.org article text before applying the same availability parser.

News sentiment sources use the dedicated `news_sentiment` adapter. It extracts
Schema.org `NewsArticle` / `Article` headline, description, and body fields when
available, separates structured article fields before scoring, and falls back to
static page text for BBC/FIFA news pages.

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
  generate_ai_report = $true
  ai_report_provider = "gpt"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/predictions/from-sources -ContentType "application/json" -Body $body
```

The homepage includes the same flow behind a browser form. Choose home/away teams and source scope, then run the crawl-and-predict path through the Next.js proxy route:

- Browser route: `POST /api/predictions/from-sources`
- Backend route: `POST /predictions/from-sources`

Set `generate_ai_report=true` with `ai_report_provider` as `gpt` or `deepseek`
to persist a review-only AI report alongside the source-backed prediction.
The report stores the Prediction Engine output and validated facts as
`input_summary`; it does not change probabilities, weights, or source facts.

`decimal_odds` facts now influence the Prediction Dataset when both teams have
market prices: lower decimal odds increase the team's market strength factor,
raise attack index, and reduce defensive weakness before Monte Carlo simulation.
BetExplorer-style static match rows with `data-odd` 1X2 prices are parsed by
the dedicated `betexplorer_odds` adapter into home/draw/away facts, so captured
marketplace HTML can produce team-scoped odds instead of only loose market price
samples.
OddsPortal uses the dedicated `oddsportal_odds` adapter for static match-line
prices and embedded market price fragments, while still treating dynamic
rendering as a source availability constraint.
OddsChecker is configured as an additional odds comparison crawl target using
the dedicated `oddschecker_odds` adapter, including decimal and fractional
price parsing for 1X2 match cards.

Team-scoped injury segments such as `Brazil: Neymar doubtful, Vinicius Junior
suspended` emit `team_unavailable_player_count` facts. Those facts reduce the
team's attack index and increase defensive weakness before simulation.

Team-scoped news segments such as `Brazil: confident boost. Croatia: injury
concern pressure.` and inline clauses such as `Brazil injury concern but Morocco
confident` emit `team_news_sentiment` facts. Positive sentiment applies a small
attack boost and defensive weakness reduction; negative sentiment applies the
inverse.

Player squad pages emit `player_presence` plus `team_listed_player_count` facts
when a team can be inferred from text or source name. When both teams have squad
counts, the Prediction Dataset applies a small squad-depth adjustment.
The `espn_team_rosters` adapter can start from ESPN's team index, discover team
IDs, fetch each roster JSON endpoint, and emit player-level facts without
manually listing one squad page per team.
Transfermarkt's World Cup squad page is configured as a secondary player-data
target using the dedicated `transfermarkt_squads` adapter for squad/player
cross-checking.
The official FIFA teams fallback uses the dedicated `fifa_teams` adapter to
extract `SportsTeam` metadata into `team_presence` facts for cross-checking.
Delete the matching file under `.scratch/source-snapshots/` when an operator
needs to force an immediate ESPN discovery refresh.

Saved prediction records can be reviewed with their source-backed evidence:

- Backend history route: `GET /predictions`
- Backend detail route: `GET /predictions/{id}/record`
- Frontend history route: `/predictions`
- Frontend detail route: `/predictions/{id}` shows the saved Prediction
  Dataset, Source Snapshot evidence, and persisted Validated Facts.

Pipeline jobs can be inspected and run from the browser:

- Backend jobs route: `GET /jobs`
- Backend run route: `POST /jobs/{job_id}/run`
- Frontend jobs route: `/jobs`
- Registered jobs: `ingest-sources`, `validate-sources`, `create-source-backed-prediction`

Manual runs are always available. Background interval scheduling is opt-in:

```powershell
$env:ENABLE_SCHEDULER = "true"
docker compose up -d --build backend
```

When enabled, `/jobs` reports scheduler state and schedules each registered job
on its configured target interval.

FIFA, Transfermarkt, OddsPortal, OddsChecker, BBC, and Elo pages are configured
as crawl targets. Dedicated parsers should be added as separate adapters when a
source needs more than static page capture; current dedicated adapters
cover ESPN discovery, Schema.org schedules, FIFA ranking, Sports Mole injuries,
Transfermarkt injuries, injury-news fallbacks, news sentiment, and World
Football Elo, plus OddsPortal/BetExplorer/OddsChecker odds and Transfermarkt
squad rows. The local source catalog no longer uses the generic `webpage`
adapter.
