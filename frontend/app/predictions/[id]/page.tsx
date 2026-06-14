type Scoreline = {
  home_goals: number;
  away_goals: number;
  probability: number;
};

type Prediction = {
  id: string;
  home_team: string;
  away_team: string;
  weight_version: string;
  simulation_count: number;
  expected_goals: Record<string, number>;
  probabilities: {
    home_win: number;
    draw: number;
    away_win: number;
  };
  top_scorelines: Scoreline[];
  confidence_level: string;
};

type PredictionDataset = {
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

type SourceSummary = {
  ingested_source_count: number;
  snapshot_count: number;
  normalized_fact_count: number;
  validated_fact_count: number;
  conflict_count: number;
};

type SourceEvidence = {
  source_name: string;
  category: string | null;
  status: string;
  snapshot_path: string | null;
  content_hash: string | null;
  item_count: number;
  fact_count: number;
  match_count: number;
  message: string | null;
};

type ValidatedFact = {
  fact_type: string;
  entity_key: string;
  status: string;
  value: unknown;
  sources: string[];
  conflicting_values: Record<string, string[]>;
};

type PredictionRecord = {
  prediction: Prediction;
  dataset: PredictionDataset | null;
  source_summary: SourceSummary | null;
  source_evidence: SourceEvidence[];
  validated_facts: ValidatedFact[];
};

type PageProps = {
  params: Promise<{ id: string }>;
};

async function fetchPredictionRecord(id: string): Promise<PredictionRecord | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/predictions/${id}/record`, {
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

export default async function PredictionDetailPage({ params }: PageProps) {
  const { id } = await params;
  const record = await fetchPredictionRecord(id);

  if (!record) {
    return (
      <main className="shell">
        <section className="prediction-panel">
          <h1>Prediction not found</h1>
          <p className="summary compact">
            The requested prediction record is not available in the backend
            repository.
          </p>
        </section>
      </main>
    );
  }

  const { prediction, dataset, source_summary: sourceSummary } = record;
  const validatedFacts = record.validated_facts ?? [];

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Prediction evidence detail</p>
        <h1>
          {prediction.home_team} vs {prediction.away_team}
        </h1>
        <p className="summary">
          Prediction ID <code>{prediction.id}</code>. Weight version{" "}
          <code>{prediction.weight_version}</code>. This detail page separates
          the probability output from the source-backed dataset and snapshot
          evidence used to construct it.
        </p>
      </section>

      <section className="prediction-panel prediction-detail-panel">
        <div>
          <p className="eyebrow">Monte Carlo output</p>
          <h2>Confidence {prediction.confidence_level}</h2>
          <p className="summary compact">
            {prediction.simulation_count.toLocaleString()} simulations. Expected
            goals: {prediction.expected_goals.home.toFixed(2)} -{" "}
            {prediction.expected_goals.away.toFixed(2)}.
          </p>
        </div>
        <div className="probability-grid">
          <div>
            <p className="label">Home win</p>
            <strong>{percent(prediction.probabilities.home_win)}</strong>
          </div>
          <div>
            <p className="label">Draw</p>
            <strong>{percent(prediction.probabilities.draw)}</strong>
          </div>
          <div>
            <p className="label">Away win</p>
            <strong>{percent(prediction.probabilities.away_win)}</strong>
          </div>
          <div>
            <p className="label">Top scorelines</p>
            <strong>{prediction.top_scorelines.length}</strong>
          </div>
        </div>
        <ol className="scorelines">
          {prediction.top_scorelines.map((scoreline) => (
            <li
              key={`${scoreline.home_goals}-${scoreline.away_goals}-${scoreline.probability}`}
            >
              <span>
                {scoreline.home_goals}-{scoreline.away_goals}
              </span>
              <span>{percent(scoreline.probability)}</span>
            </li>
          ))}
        </ol>
      </section>

      {sourceSummary ? (
        <section className="source-ops-summary detail-summary">
          <article>
            <p className="label">Sources</p>
            <strong>{sourceSummary.ingested_source_count}</strong>
          </article>
          <article>
            <p className="label">Snapshots</p>
            <strong>{sourceSummary.snapshot_count}</strong>
          </article>
          <article>
            <p className="label">Facts</p>
            <strong>{sourceSummary.normalized_fact_count}</strong>
          </article>
          <article>
            <p className="label">Validated</p>
            <strong>{sourceSummary.validated_fact_count}</strong>
          </article>
        </section>
      ) : null}

      {dataset ? (
        <section className="dataset-grid detail-dataset">
          <article>
            <p className="label">{dataset.home_team}</p>
            <strong>{dataset.home.attack_index.toFixed(3)}</strong>
            <span>attack index</span>
            <span>{dataset.home.defense_weakness.toFixed(3)} defense weakness</span>
          </article>
          <article>
            <p className="label">{dataset.away_team}</p>
            <strong>{dataset.away.attack_index.toFixed(3)}</strong>
            <span>attack index</span>
            <span>{dataset.away.defense_weakness.toFixed(3)} defense weakness</span>
          </article>
          <article>
            <p className="label">Home advantage</p>
            <strong>{dataset.home_advantage.toFixed(3)}</strong>
            <span>{dataset.conflict_count} conflict penalty</span>
          </article>
        </section>
      ) : null}

      <section className="source-category">
        <div className="source-category-header">
          <p className="label">Validated facts</p>
          <span>{validatedFacts.length} records</span>
        </div>
        {validatedFacts.length ? (
          <div className="evidence-grid">
            {validatedFacts.slice(0, 24).map((fact) => (
              <article
                className="evidence-card"
                key={`${fact.fact_type}-${fact.entity_key}-${formatFactValue(fact.value)}`}
              >
                <span className="source-pill source-pill-live">{fact.status}</span>
                <h2>{fact.entity_key}</h2>
                <p>{fact.fact_type.replaceAll("_", " ")}</p>
                <p>Value: {formatFactValue(fact.value)}</p>
                <p>Sources: {fact.sources.join(", ") || "none"}</p>
                {Object.keys(fact.conflicting_values).length ? (
                  <code>{JSON.stringify(fact.conflicting_values)}</code>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="summary compact">
            This record has no persisted validated facts.
          </p>
        )}
      </section>

      <section className="source-category">
        <div className="source-category-header">
          <p className="label">Source evidence</p>
          <span>{record.source_evidence.length} records</span>
        </div>
        {record.source_evidence.length ? (
          <div className="evidence-grid">
            {record.source_evidence.map((evidence) => (
              <article className="evidence-card" key={evidence.source_name}>
                <span className="source-pill source-pill-live">
                  {evidence.status}
                </span>
                <h2>{evidence.source_name}</h2>
                <p>
                  {evidence.category ?? "uncategorized"} / facts{" "}
                  {evidence.fact_count} / matches {evidence.match_count}
                </p>
                {evidence.snapshot_path ? <p>{evidence.snapshot_path}</p> : null}
                {evidence.content_hash ? (
                  <code>{evidence.content_hash.slice(0, 16)}</code>
                ) : null}
                {evidence.message ? <p>{evidence.message}</p> : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="summary compact">
            This record has no persisted source snapshot evidence.
          </p>
        )}
      </section>
    </main>
  );
}

function formatFactValue(value: unknown) {
  if (value === null || value === undefined) {
    return "none";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}
