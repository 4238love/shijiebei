type Methodology = {
  prediction_engine: {
    principle: string;
    inputs: string[];
  };
  monte_carlo: {
    default_simulations: number;
    distribution: string;
    outputs: string[];
  };
  ai_analysis: {
    providers: string[];
    role: string;
    can_change_probabilities: boolean;
    can_auto_activate_weights: boolean;
  };
  cross_source_validation: {
    statuses: string[];
    principle: string;
  };
  backtest_run: {
    metrics: string[];
  };
};

async function fetchMethodology(): Promise<Methodology | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/methodology`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

export default async function MethodologyPage() {
  const methodology = await fetchMethodology();

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Technical methodology</p>
        <h1>Auditable prediction stack</h1>
        <p className="summary">
          The visual framing can be cinematic, but the system boundaries stay
          explicit: statistics produce probabilities, AI produces explanations.
        </p>
      </section>

      {methodology ? (
        <section className="method-grid">
          <article>
            <p className="label">Prediction Engine</p>
            <h2>Probability owner</h2>
            <p>{methodology.prediction_engine.principle}</p>
          </article>
          <article>
            <p className="label">Monte Carlo</p>
            <h2>{methodology.monte_carlo.default_simulations.toLocaleString()} runs</h2>
            <p>{methodology.monte_carlo.distribution}</p>
          </article>
          <article>
            <p className="label">DeepSeek / GPT</p>
            <h2>Report only</h2>
            <p>{methodology.ai_analysis.role}</p>
          </article>
          <article>
            <p className="label">Source conflicts</p>
            <h2>{methodology.cross_source_validation.statuses.join(" / ")}</h2>
            <p>{methodology.cross_source_validation.principle}</p>
          </article>
          <article className="wide">
            <p className="label">Backtest Run</p>
            <h2>Evidence loop</h2>
            <ul>
              {methodology.backtest_run.metrics.map((metric) => (
                <li key={metric}>{metric}</li>
              ))}
            </ul>
          </article>
        </section>
      ) : (
        <section className="prediction-panel">
          <h2>Methodology API unavailable</h2>
          <p className="summary compact">Start the backend service to load methodology data.</p>
        </section>
      )}
    </main>
  );
}
