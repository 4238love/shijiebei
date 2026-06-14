type AIReport = {
  provider_name: string;
  model_name: string;
  content: string;
  input_summary: {
    match: string;
    confidence_level: string;
    probabilities: Record<string, number>;
    conflict_statuses: Array<{ status: string; entity_key: string }>;
  };
};

async function createDemoReport(providerName: "gpt" | "deepseek"): Promise<AIReport | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/ai-reports`, {
      method: "POST",
      cache: "no-store",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        provider_name: providerName,
        prediction: {
          home_team: "Brazil",
          away_team: "Croatia",
          weight_version: "baseline",
          simulation_count: 10000,
          expected_goals: { home: 1.85, away: 0.95 },
          probabilities: { home_win: 0.58, draw: 0.24, away_win: 0.18 },
          top_scorelines: [{ home_goals: 1, away_goals: 0, probability: 0.12 }],
          confidence_level: "A",
        },
        validated_facts: [
          {
            fact_type: "injury_availability",
            entity_key: "Neymar",
            status: "conflicting",
            value: "doubtful",
            sources: ["injury-primary", "injury-secondary"],
            conflicting_values: {
              doubtful: ["injury-primary"],
              available: ["injury-secondary"],
            },
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

export default async function ReportsPage() {
  const [gptReport, deepseekReport] = await Promise.all([
    createDemoReport("gpt"),
    createDemoReport("deepseek"),
  ]);
  const reports = [gptReport, deepseekReport].filter(Boolean) as AIReport[];

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">AI Analysis Report</p>
        <h1>Narrative layer, not probability owner</h1>
        <p className="summary">
          Reports receive structured predictions and Validated Facts. They
          explain the run; they do not mutate probabilities or weights.
        </p>
      </section>

      {reports.length ? (
        <section className="report-grid">
          {reports.map((report) => (
            <article key={`${report.provider_name}-${report.model_name}`}>
              <p className="label">
                {report.provider_name} / {report.model_name}
              </p>
              <h2>{report.input_summary.match}</h2>
              <p>{report.content}</p>
              <div className="factor-grid">
                <span>
                  <b>Home win</b>
                  {percent(report.input_summary.probabilities.home_win)}
                </span>
                <span>
                  <b>Confidence</b>
                  {report.input_summary.confidence_level}
                </span>
                <span>
                  <b>Facts reviewed</b>
                  {report.input_summary.conflict_statuses.length}
                </span>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <section className="prediction-panel">
          <h2>AI Report API unavailable</h2>
          <p className="summary compact">Start the backend service to generate demo reports.</p>
        </section>
      )}
    </main>
  );
}
