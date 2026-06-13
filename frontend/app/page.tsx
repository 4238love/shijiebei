type HealthPayload = {
  status: "ok" | "degraded";
  service: string;
  database: "ok" | "unavailable";
};

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

async function fetchBackendHealth(): Promise<HealthPayload> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/health`, {
      cache: "no-store",
    });

    if (!response.ok) {
      return {
        status: "degraded",
        service: "backend",
        database: "unavailable",
      };
    }

    return response.json();
  } catch {
    return {
      status: "degraded",
      service: "backend",
      database: "unavailable",
    };
  }
}

async function fetchDemoPrediction(): Promise<PredictionPayload | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/predictions`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({
        dataset: {
          home_team: "Brazil",
          away_team: "Croatia",
          home: { attack_index: 1.35, defense_weakness: 0.82 },
          away: { attack_index: 0.96, defense_weakness: 1.05 },
          home_advantage: 1.08,
          conflict_count: 0,
        },
        weight_version: {
          name: "baseline",
          factors: {},
        },
        simulation_count: 10000,
        seed: 20260613,
      }),
    });

    if (!response.ok) {
      return null;
    }

    return response.json();
  } catch {
    return null;
  }
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export default async function Home() {
  const healthPromise = fetchBackendHealth();
  const predictionPromise = fetchDemoPrediction();
  const [health, prediction] = await Promise.all([healthPromise, predictionPromise]);
  const backendReady = health.status === "ok";

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Deep prediction methodology</p>
        <h1>World Cup Prediction Tool</h1>
        <p className="summary">
          A Docker Compose web system for source snapshots, statistical match
          predictions, DeepSeek/GPT analysis reports, and backtest runs.
        </p>
      </section>

      <section className="status-grid" aria-label="System health">
        <article className="status-card">
          <span className={backendReady ? "signal signal-ok" : "signal"} />
          <div>
            <p className="label">Backend</p>
            <h2>{health.status}</h2>
          </div>
        </article>

        <article className="status-card">
          <span
            className={health.database === "ok" ? "signal signal-ok" : "signal"}
          />
          <div>
            <p className="label">PostgreSQL</p>
            <h2>{health.database}</h2>
          </div>
        </article>
      </section>

      <section className="prediction-panel" aria-label="Demo match prediction">
        <div>
          <p className="eyebrow">Monte Carlo simulation</p>
          <h2>
            {prediction
              ? `${prediction.home_team} vs ${prediction.away_team}`
              : "Prediction API unavailable"}
          </h2>
          <p className="summary compact">
            Demo Match Prediction generated through the backend API. The
            Prediction Engine owns probabilities; AI reports will be layered on
            top in a later slice.
          </p>
        </div>

        {prediction ? (
          <>
            <div className="probability-grid">
              <div>
                <p className="label">Home win</p>
                <strong>{formatPercent(prediction.probabilities.home_win)}</strong>
              </div>
              <div>
                <p className="label">Draw</p>
                <strong>{formatPercent(prediction.probabilities.draw)}</strong>
              </div>
              <div>
                <p className="label">Away win</p>
                <strong>{formatPercent(prediction.probabilities.away_win)}</strong>
              </div>
              <div>
                <p className="label">Confidence</p>
                <strong>{prediction.confidence_level}</strong>
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
                  <span>{formatPercent(scoreline.probability)}</span>
                </li>
              ))}
            </ol>
          </>
        ) : (
          <p className="summary compact">
            Start the backend service to generate the first fixture-backed Match
            Prediction.
          </p>
        )}
      </section>
    </main>
  );
}
