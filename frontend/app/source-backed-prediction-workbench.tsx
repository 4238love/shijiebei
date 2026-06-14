"use client";

import { FormEvent, useMemo, useState } from "react";

type Scoreline = {
  home_goals: number;
  away_goals: number;
  probability: number;
};

type PredictionPayload = {
  id: string;
  home_team: string;
  away_team: string;
  probabilities: {
    home_win: number;
    draw: number;
    away_win: number;
  };
  top_scorelines: Scoreline[];
  confidence_level: string;
};

type PredictionDatasetPayload = {
  home_team: string;
  away_team: string;
  home: {
    attack_index: number;
    defense_weakness: number;
  };
  away: {
    attack_index: number;
    defense_weakness: number;
  };
  home_advantage: number;
  conflict_count: number;
};

type SourceSummaryPayload = {
  ingested_source_count: number;
  snapshot_count: number;
  normalized_fact_count: number;
  validated_fact_count: number;
  conflict_count: number;
};

type SourceBackedPredictionPayload = {
  prediction: PredictionPayload;
  dataset: PredictionDatasetPayload;
  source_summary: SourceSummaryPayload;
};

type SourceCategoryOption = {
  value: string;
  label: string;
};

const SOURCE_CATEGORY_OPTIONS: SourceCategoryOption[] = [
  { value: "", label: "All configured sources" },
  { value: "ranking", label: "Ranking" },
  { value: "team_form", label: "Team form" },
  { value: "injury", label: "Injury" },
  { value: "odds", label: "Odds" },
  { value: "news_sentiment", label: "News sentiment" },
  { value: "player", label: "Player data" },
  { value: "schedule", label: "Schedule" },
];

type Props = {
  backendReady: boolean;
};

export function SourceBackedPredictionWorkbench({ backendReady }: Props) {
  const [homeTeam, setHomeTeam] = useState("Brazil");
  const [awayTeam, setAwayTeam] = useState("Croatia");
  const [category, setCategory] = useState("");
  const [simulationCount, setSimulationCount] = useState(1000);
  const [prediction, setPrediction] =
    useState<SourceBackedPredictionPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const selectedCategoryLabel = useMemo(
    () =>
      SOURCE_CATEGORY_OPTIONS.find((option) => option.value === category)?.label ??
      "Custom source set",
    [category],
  );

  async function runPrediction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsRunning(true);

    try {
      const trimmedHomeTeam = homeTeam.trim();
      const trimmedAwayTeam = awayTeam.trim();
      if (!trimmedHomeTeam || !trimmedAwayTeam) {
        throw new Error("Both team names are required.");
      }

      const response = await fetch("/api/predictions/from-sources", {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify({
          home_team: trimmedHomeTeam,
          away_team: trimmedAwayTeam,
          category: category || undefined,
          simulation_count: simulationCount,
          seed: 20260614,
        }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Prediction failed with HTTP ${response.status}`);
      }

      setPrediction((await response.json()) as SourceBackedPredictionPayload);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Source-backed prediction failed.",
      );
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <section
      className="prediction-panel prediction-workbench"
      aria-label="Source-backed match prediction"
    >
      <div className="prediction-copy">
        <p className="eyebrow">Live source-backed prediction</p>
        <h2>
          {prediction
            ? `${prediction.prediction.home_team} vs ${prediction.prediction.away_team}`
            : "Choose teams, then crawl sources"}
        </h2>
        <p className="summary compact">
          This button validates configured web sources, builds a Prediction
          Dataset from Validated Facts, then runs the Monte Carlo Prediction
          Engine. DeepSeek/GPT stays reserved for reports and weight
          recommendations.
        </p>
      </div>

      <form className="prediction-form" onSubmit={runPrediction}>
        <label>
          <span className="label">Home team</span>
          <input
            value={homeTeam}
            onChange={(event) => setHomeTeam(event.target.value)}
            required
          />
        </label>
        <label>
          <span className="label">Away team</span>
          <input
            value={awayTeam}
            onChange={(event) => setAwayTeam(event.target.value)}
            required
          />
        </label>
        <label>
          <span className="label">Source scope</span>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            {SOURCE_CATEGORY_OPTIONS.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">Simulations</span>
          <input
            min={100}
            max={20000}
            step={100}
            type="number"
            value={simulationCount}
            onChange={(event) => setSimulationCount(Number(event.target.value))}
            required
          />
        </label>
        <button disabled={!backendReady || isRunning} type="submit">
          {isRunning ? "Crawling and predicting" : "Run source prediction"}
        </button>
        <p className="summary compact prediction-scope">
          Scope: {selectedCategoryLabel}. Full source runs can take longer
          because snapshots are captured before probabilities are produced.
        </p>
      </form>

      {error ? <p className="source-ops-error">{error}</p> : null}

      {prediction ? (
        <>
          <div className="probability-grid">
            <div>
              <p className="label">Home win</p>
              <strong>
                {formatPercent(prediction.prediction.probabilities.home_win)}
              </strong>
            </div>
            <div>
              <p className="label">Draw</p>
              <strong>{formatPercent(prediction.prediction.probabilities.draw)}</strong>
            </div>
            <div>
              <p className="label">Away win</p>
              <strong>
                {formatPercent(prediction.prediction.probabilities.away_win)}
              </strong>
            </div>
            <div>
              <p className="label">Confidence</p>
              <strong>{prediction.prediction.confidence_level}</strong>
            </div>
          </div>

          <div className="source-ops-summary prediction-source-summary">
            <article>
              <p className="label">Sources</p>
              <strong>{prediction.source_summary.ingested_source_count}</strong>
            </article>
            <article>
              <p className="label">Snapshots</p>
              <strong>{prediction.source_summary.snapshot_count}</strong>
            </article>
            <article>
              <p className="label">Facts</p>
              <strong>{prediction.source_summary.normalized_fact_count}</strong>
            </article>
            <article>
              <p className="label">Validated</p>
              <strong>{prediction.source_summary.validated_fact_count}</strong>
            </article>
          </div>

          <div className="dataset-grid">
            <article>
              <p className="label">{prediction.dataset.home_team}</p>
              <strong>{prediction.dataset.home.attack_index.toFixed(3)}</strong>
              <span>attack index</span>
              <span>
                {prediction.dataset.home.defense_weakness.toFixed(3)} defense
                weakness
              </span>
            </article>
            <article>
              <p className="label">{prediction.dataset.away_team}</p>
              <strong>{prediction.dataset.away.attack_index.toFixed(3)}</strong>
              <span>attack index</span>
              <span>
                {prediction.dataset.away.defense_weakness.toFixed(3)} defense
                weakness
              </span>
            </article>
            <article>
              <p className="label">Conflict penalty</p>
              <strong>{prediction.dataset.conflict_count}</strong>
              <span>feeds Confidence Level</span>
            </article>
          </div>

          <ol className="scorelines">
            {prediction.prediction.top_scorelines.map((scoreline) => (
              <li
                key={`${scoreline.home_goals}-${scoreline.away_goals}-${scoreline.probability}`}
              >
                <span>
                  {scoreline.home_goals}-{scoreline.away_goals}
                </span>
                <span>{formatPercent(scoreline.probability)}</span>
              </li>
            ))}
          </ol>

          <a
            className="evidence-link"
            href={`/predictions/${prediction.prediction.id}`}
          >
            Open prediction evidence detail
          </a>
        </>
      ) : (
        <p className="summary compact prediction-empty-state">
          Start with Ranking for a fast smoke test, or All configured sources for
          the complete crawl-and-validate path.
        </p>
      )}
    </section>
  );
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}
