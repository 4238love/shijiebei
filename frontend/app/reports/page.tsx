import {
  localizeTeamNamesInText,
  matchTextLabel,
} from "../team-labels";

type AIReport = {
  id: string;
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
        <p className="eyebrow">AI 分析报告</p>
        <h1>负责解释，不直接改写概率</h1>
        <p className="summary">
          报告接收结构化预测和已验证事实，只解释本次运行的依据，
          不会直接修改概率或权重。
        </p>
      </section>

      {reports.length ? (
        <section className="report-grid">
          {reports.map((report) => (
            <article key={report.id}>
              <p className="label">
                {report.provider_name} / {report.model_name}
              </p>
              <h2>{matchTextLabel(report.input_summary.match)}</h2>
              <p>{localizeTeamNamesInText(report.content)}</p>
              <div className="factor-grid">
                <span>
                  <b>主胜</b>
                  {percent(report.input_summary.probabilities.home_win)}
                </span>
                <span>
                  <b>置信等级</b>
                  {report.input_summary.confidence_level}
                </span>
                <span>
                  <b>复核事实</b>
                  {report.input_summary.conflict_statuses.length}
                </span>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <section className="prediction-panel">
          <h2>AI 报告 API 不可用</h2>
          <p className="summary compact">启动后端服务后才能生成示例报告。</p>
        </section>
      )}
    </main>
  );
}
