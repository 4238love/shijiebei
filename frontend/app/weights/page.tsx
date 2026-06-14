type WeightVersion = {
  name: string;
  factors: Record<string, number>;
};

async function fetchActiveWeightVersion(): Promise<WeightVersion | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/weights/active`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

export default async function WeightsPage() {
  const active = await fetchActiveWeightVersion();

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Weight Review</p>
        <h1>AI can suggest. Operators activate.</h1>
        <p className="summary">
          DeepSeek and GPT may produce Weight Recommendations, but the active
          Weight Version changes only after review and backtest evidence.
        </p>
      </section>

      {active ? (
        <section className="method-grid">
          <article className="wide">
            <p className="label">Active Weight Version</p>
            <h2>{active.name}</h2>
            <div className="factor-grid">
              {Object.entries(active.factors).map(([name, value]) => (
                <span key={name}>
                  <b>{name}</b>
                  {value}
                </span>
              ))}
            </div>
          </article>
          <article>
            <p className="label">Recommendation gate</p>
            <h2>Proposed</h2>
            <p>
              A model-generated recommendation is stored as proposed and has no
              effect on predictions.
            </p>
          </article>
          <article>
            <p className="label">Approval gate</p>
            <h2>Backtest required</h2>
            <p>
              Approval requires a reviewer, a backtest reference, and a new
              version name before factors can activate.
            </p>
          </article>
        </section>
      ) : (
        <section className="prediction-panel">
          <h2>Weight API unavailable</h2>
          <p className="summary compact">Start the backend service to inspect active weights.</p>
        </section>
      )}
    </main>
  );
}
