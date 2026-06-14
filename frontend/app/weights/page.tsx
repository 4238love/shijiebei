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

const FACTOR_LABELS: Record<string, string> = {
  base_goal_rate: "基础进球率",
  home_goal_multiplier: "主场进球倍率",
};

export default async function WeightsPage() {
  const active = await fetchActiveWeightVersion();

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">权重复核</p>
        <h1>AI 可以建议，操作者负责启用</h1>
        <p className="summary">
          DeepSeek 和 GPT 可以生成权重建议，但只有经过人工复核并提供回测证据后，
          当前权重版本才会变更。
        </p>
      </section>

      {active ? (
        <section className="method-grid">
          <article className="wide">
            <p className="label">当前权重版本</p>
            <h2>{active.name}</h2>
            <div className="factor-grid">
              {Object.entries(active.factors).map(([name, value]) => (
                <span key={name}>
                  <b>{factorLabel(name)}</b>
                  {value}
                </span>
              ))}
            </div>
          </article>
          <article>
            <p className="label">建议关口</p>
            <h2>仅保存为候选</h2>
            <p>
              模型生成的建议只会以候选状态保存，不会直接影响预测结果。
            </p>
          </article>
          <article>
            <p className="label">审批关口</p>
            <h2>必须提供回测</h2>
            <p>
              启用前必须填写复核人、回测引用和新的版本名，权重因子才会生效。
            </p>
          </article>
        </section>
      ) : (
        <section className="prediction-panel">
          <h2>权重 API 不可用</h2>
          <p className="summary compact">启动后端服务后才能查看当前权重。</p>
        </section>
      )}
    </main>
  );
}

function factorLabel(factor: string) {
  return FACTOR_LABELS[factor] ?? factor.replaceAll("_", " ");
}
