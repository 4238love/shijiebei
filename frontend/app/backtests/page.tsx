type BacktestRun = {
  id: string;
  match_count: number;
  outcome_hit_rate: number;
  brier_score: number;
  log_loss: number;
  scoreline_top_n_hit_rate: number;
  segments: Record<string, { match_count: number; outcome_hit_rate: number }>;
};

async function createDemoBacktest(): Promise<BacktestRun | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/backtests`, {
      method: "POST",
      cache: "no-store",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        scoreline_top_n: 1,
        cases: [
          {
            prediction: {
              home_team: "Brazil",
              away_team: "Croatia",
              weight_version: "baseline",
              simulation_count: 10000,
              expected_goals: { home: 1.8, away: 0.8 },
              probabilities: { home_win: 0.6, draw: 0.25, away_win: 0.15 },
              top_scorelines: [{ home_goals: 1, away_goals: 0, probability: 0.12 }],
              confidence_level: "A",
            },
            actual_result: { home_goals: 1, away_goals: 0 },
            conflict_status: "confirmed",
          },
          {
            prediction: {
              home_team: "Argentina",
              away_team: "France",
              weight_version: "baseline",
              simulation_count: 10000,
              expected_goals: { home: 1.4, away: 1.2 },
              probabilities: { home_win: 0.2, draw: 0.3, away_win: 0.5 },
              top_scorelines: [{ home_goals: 0, away_goals: 1, probability: 0.1 }],
              confidence_level: "B",
            },
            actual_result: { home_goals: 0, away_goals: 0 },
            conflict_status: "conflicting",
          },
        ],
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

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export default async function BacktestsPage() {
  const run = await createDemoBacktest();

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Backtest Run</p>
        <h1>Evidence before confidence</h1>
        <p className="summary">
          Backtests replay saved Match Predictions against actual results, using
          the original weight version and conflict status context.
        </p>
      </section>

      {run ? (
        <section className="metric-board">
          <article className="metric-card wide-card">
            <p className="label">Run id</p>
            <h2>{run.id}</h2>
            <p>Current demo run uses two cases and top-1 scoreline evaluation.</p>
          </article>
          <article className="metric-card">
            <p className="label">Outcome hit rate</p>
            <strong>{percent(run.outcome_hit_rate)}</strong>
          </article>
          <article className="metric-card">
            <p className="label">Scoreline hit rate</p>
            <strong>{percent(run.scoreline_top_n_hit_rate)}</strong>
          </article>
          <article className="metric-card">
            <p className="label">Brier score</p>
            <strong>{run.brier_score.toFixed(4)}</strong>
          </article>
          <article className="metric-card">
            <p className="label">Log loss</p>
            <strong>{run.log_loss.toFixed(4)}</strong>
          </article>
          <article className="metric-card wide-card">
            <p className="label">Conflict segments</p>
            <div className="segment-list">
              {Object.entries(run.segments).map(([status, segment]) => (
                <span key={status}>
                  {status}: {segment.match_count} match, {percent(segment.outcome_hit_rate)}
                </span>
              ))}
            </div>
          </article>
        </section>
      ) : (
        <section className="prediction-panel">
          <h2>Backtest API unavailable</h2>
          <p className="summary compact">Start the backend service to create a demo run.</p>
        </section>
      )}
    </main>
  );
}
