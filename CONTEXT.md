# World Cup Prediction Tool

This context defines the domain language for a football match prediction tool that combines statistical probability modeling with AI-generated analysis reports.

## Language

**Match Prediction**:
A prediction result for one football match, including win/draw/loss probabilities, likely scorelines, confidence level, and explanatory analysis.
_Avoid_: Pick, guess, bet tip

**Prediction Engine**:
The statistical system that produces probabilities and score distributions from match data.
_Avoid_: AI guesser, oracle

**AI Analysis Report**:
A natural-language explanation generated from structured prediction results and match data.
_Avoid_: AI prediction, AI pick

**Data Source**:
A website, API, file, or manually maintained feed that provides match schedules, team form, injuries, rankings, odds, or results.
_Avoid_: Raw page, scrape target

**Data Source Adapter**:
An isolated connector for one data source that fetches source material and converts it into the project's normalized match data language.
_Avoid_: Scraper script, crawler blob

**Source Snapshot**:
A saved copy of fetched source material used for debugging, replaying, and explaining how a prediction dataset was produced.
_Avoid_: Cache junk, temp HTML

**Prediction Dataset**:
The cleaned and normalized data used by the prediction engine for one prediction run.
_Avoid_: Live scrape result, page parse

**Injury Feed**:
A data source category that provides unavailable, doubtful, suspended, or returning player information relevant to a match prediction.
_Avoid_: Injury rumor

**Odds Feed**:
A data source category that provides market prices or implied probabilities for match outcomes, scorelines, totals, or handicaps.
_Avoid_: Betting tip

**News Sentiment Feed**:
A data source category that provides recent news material used to estimate team morale, tactical disruption, pressure, or public narrative.
_Avoid_: Hype, media noise

**Player Dataset**:
Normalized player-level data used to estimate team strength, availability impact, and matchup-specific adjustments.
_Avoid_: Player trivia

**Cross-Source Validation**:
The process of comparing multiple data sources for the same fact and assigning a usable confidence score or conflict status.
_Avoid_: Blind merge, source voting

**Source Priority**:
A data-type-specific ordering that decides which data source is more trusted when multiple sources disagree.
_Avoid_: Global source ranking

**Source Catalog**:
A configured list of data sources grouped by category for the first-wave crawl, including schedule, team form, ranking, injury, odds, news sentiment, and player data.
_Avoid_: URL list

**Validated Fact**:
A normalized fact after cross-source validation has assigned a conflict status, selected value, and source evidence.
_Avoid_: Final truth

**Conflict Status**:
The resolved state of a normalized fact after cross-source validation, such as confirmed, conflicting, missing, or stale.
_Avoid_: Parse status

**Strategy Factor**:
A weighted football-specific condition that adjusts the prediction inputs, such as injury impact, home advantage, schedule density, or knockout pressure.
_Avoid_: Magic factor, hidden weight

**Weight Recommendation**:
An AI-generated suggestion to change strategy factor weights that has no effect until reviewed, versioned, backtested, and approved.
_Avoid_: Auto tuning, live model update

**Monte Carlo Simulation**:
A repeated scoreline simulation that turns expected goals into a probability distribution for match outcomes.
_Avoid_: Random guess

**Confidence Level**:
A coarse rating that communicates how concentrated or uncertain a match prediction is.
_Avoid_: Certainty, guarantee

**Backtest Run**:
A replay or evaluation of saved match predictions against actual results, using the prediction dataset and weight version that existed when the prediction was made.
_Avoid_: Accuracy screenshot, after-the-fact proof

**Weight Version**:
A named version of strategy factor weights used by the prediction engine for reproducible match predictions and backtest runs.
_Avoid_: Current weights
