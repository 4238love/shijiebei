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
  source_backed_prediction: {
    endpoint: string;
    principle: string;
    outputs: string[];
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
        <p className="eyebrow">技术方法论</p>
        <h1>可审计的预测技术栈</h1>
        <p className="summary">
          页面可以有视觉表现，但系统边界必须清晰：统计引擎负责概率，
          AI 只负责解释。
        </p>
      </section>

      {methodology ? (
        <section className="method-grid">
          <article>
            <p className="label">预测引擎</p>
            <h2>概率归属</h2>
            <p>比赛概率由可复现的统计预测引擎生成，AI 不直接改写概率。</p>
          </article>
          <article>
            <p className="label">蒙特卡洛</p>
            <h2>{methodology.monte_carlo.default_simulations.toLocaleString()} 次运行</h2>
            <p>基于进攻、防守、主场优势和数据冲突等输入进行比分分布模拟。</p>
          </article>
          <article>
            <p className="label">DeepSeek / GPT</p>
            <h2>只生成报告</h2>
            <p>模型只接收结构化证据用于分析说明和建议，不直接改变预测输出。</p>
          </article>
          <article>
            <p className="label">数据源冲突</p>
            <h2>
              {methodology.cross_source_validation.statuses
                .map(statusLabel)
                .join(" / ")}
            </h2>
            <p>多数据源事实会按优先级交叉验证，冲突会降低置信度而不是被忽略。</p>
          </article>
          <article>
            <p className="label">数据源驱动预测</p>
            <h2>{methodology.source_backed_prediction.endpoint}</h2>
            <p>预测记录会保存数据集、源快照和已验证事实，便于复盘。</p>
          </article>
          <article className="wide">
            <p className="label">回测运行</p>
            <h2>证据闭环</h2>
            <ul>
              {methodology.backtest_run.metrics.map((metric) => (
                <li key={metric}>{metricLabel(metric)}</li>
              ))}
            </ul>
          </article>
        </section>
      ) : (
        <section className="prediction-panel">
          <h2>方法论 API 不可用</h2>
          <p className="summary compact">启动后端服务后才能加载方法论数据。</p>
        </section>
      )}
    </main>
  );
}

function metricLabel(metric: string) {
  const labels: Record<string, string> = {
    brier_score: "Brier 分数",
    log_loss: "对数损失",
    outcome_hit_rate: "赛果命中率",
    scoreline_top_n_hit_rate: "比分 Top-N 命中率",
  };
  return labels[metric] ?? metric.replaceAll("_", " ");
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
