type SourceSummary = {
  ingested_source_count: number;
  snapshot_count: number;
  normalized_fact_count: number;
  validated_fact_count: number;
  conflict_count: number;
};

type PredictionHistoryItem = {
  id: string;
  home_team: string;
  away_team: string;
  probabilities: {
    home_win: number;
    draw: number;
    away_win: number;
  };
  confidence_level: string;
  source_summary: SourceSummary | null;
};

type PredictionHistoryPayload = {
  predictions: PredictionHistoryItem[];
};

async function fetchPredictionHistory(): Promise<PredictionHistoryPayload | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/predictions?limit=30`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export default async function PredictionsPage() {
  const history = await fetchPredictionHistory();
  const predictions = history?.predictions ?? [];

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Prediction history</p>
        <h1>Saved runs and evidence trail</h1>
        <p className="summary">
          Every source-backed run persists the Match Prediction plus the
          constructed Prediction Dataset, source summary, and snapshot evidence
          needed to audit how the probabilities were produced.
        </p>
      </section>

      {history ? (
        predictions.length ? (
          <section className="history-grid" aria-label="Saved predictions">
            {predictions.map((prediction) => (
              <a
                className="history-card"
                href={`/predictions/${prediction.id}`}
                key={prediction.id}
              >
                <span className="source-pill source-pill-live">
                  Confidence {prediction.confidence_level}
                </span>
                <h2>
                  {prediction.home_team} vs {prediction.away_team}
                </h2>
                <div className="history-probabilities">
                  <span>
                    <b>Home</b>
                    {percent(prediction.probabilities.home_win)}
                  </span>
                  <span>
                    <b>Draw</b>
                    {percent(prediction.probabilities.draw)}
                  </span>
                  <span>
                    <b>Away</b>
                    {percent(prediction.probabilities.away_win)}
                  </span>
                </div>
                {prediction.source_summary ? (
                  <p>
                    {prediction.source_summary.ingested_source_count} sources /{" "}
                    {prediction.source_summary.snapshot_count} snapshots /{" "}
                    {prediction.source_summary.validated_fact_count} validated
                    facts
                  </p>
                ) : (
                  <p>No persisted source evidence attached.</p>
                )}
              </a>
            ))}
          </section>
        ) : (
          <section className="prediction-panel">
            <h2>No saved predictions yet</h2>
            <p className="summary compact">
              Run a source-backed prediction from the homepage to create the
              first auditable record.
            </p>
          </section>
        )
      ) : (
        <section className="prediction-panel">
          <h2>Prediction history unavailable</h2>
          <p className="summary compact">
            Start the backend service to read saved Match Predictions.
          </p>
        </section>
      )}
    </main>
  );
}
