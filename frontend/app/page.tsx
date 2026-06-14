import { SourceBackedPredictionWorkbench } from "./source-backed-prediction-workbench";

type HealthPayload = {
  status: "ok" | "degraded";
  service: string;
  database: "ok" | "unavailable";
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

export default async function Home() {
  const health = await fetchBackendHealth();
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

      <SourceBackedPredictionWorkbench backendReady={backendReady} />
    </main>
  );
}
