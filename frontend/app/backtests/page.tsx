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
        <p className="eyebrow">回测运行</p>
        <h1>先有证据，再给置信度</h1>
        <p className="summary">
          回测会用真实赛果重放已保存的比赛预测，并保留原始权重版本和数据冲突状态。
        </p>
      </section>

      {run ? (
        <section className="metric-board">
          <article className="metric-card wide-card">
            <p className="label">运行 ID</p>
            <h2>{run.id}</h2>
            <p>当前演示回测包含两个样本，并使用 Top-1 比分命中评估。</p>
          </article>
          <article className="metric-card">
            <p className="label">赛果命中率</p>
            <strong>{percent(run.outcome_hit_rate)}</strong>
          </article>
          <article className="metric-card">
            <p className="label">比分命中率</p>
            <strong>{percent(run.scoreline_top_n_hit_rate)}</strong>
          </article>
          <article className="metric-card">
            <p className="label">Brier 分数</p>
            <strong>{run.brier_score.toFixed(4)}</strong>
          </article>
          <article className="metric-card">
            <p className="label">对数损失</p>
            <strong>{run.log_loss.toFixed(4)}</strong>
          </article>
          <article className="metric-card wide-card">
            <p className="label">冲突分组</p>
            <div className="segment-list">
              {Object.entries(run.segments).map(([status, segment]) => (
                <span key={status}>
                  {statusLabel(status)}：{segment.match_count} 场，
                  {percent(segment.outcome_hit_rate)}
                </span>
              ))}
            </div>
          </article>
        </section>
      ) : (
        <section className="prediction-panel">
          <h2>回测 API 不可用</h2>
          <p className="summary compact">启动后端服务后才能创建演示回测。</p>
        </section>
      )}
    </main>
  );
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    confirmed: "已确认",
    conflicting: "有冲突",
    missing: "缺失",
    stale: "过期",
  };
  return labels[status] ?? status;
}
