import { matchLabel } from "../team-labels";

type SourceSummary = {
  ingested_source_count: number;
  snapshot_count: number;
  normalized_fact_count: number;
  validated_fact_count: number;
  conflict_count: number;
};

type PredictionHistoryItem = {
  id: string;
  home_team: string;
  away_team: string;
  probabilities: {
    home_win: number;
    draw: number;
    away_win: number;
  };
  confidence_level: string;
  source_summary: SourceSummary | null;
};

type PredictionHistoryPayload = {
  predictions: PredictionHistoryItem[];
};

async function fetchPredictionHistory(): Promise<PredictionHistoryPayload | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/predictions?limit=30`, {
      cache: "no-store",
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

export default async function PredictionsPage() {
  const history = await fetchPredictionHistory();
  const predictions = history?.predictions ?? [];

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">预测历史</p>
        <h1>已保存运行和证据链</h1>
        <p className="summary">
          每次基于数据源的运行都会保存比赛预测、构建出的预测数据集、
          数据源摘要和快照证据，用于审计概率是如何生成的。
        </p>
      </section>

      {history ? (
        predictions.length ? (
          <section className="history-grid" aria-label="已保存预测">
            {predictions.map((prediction) => (
              <a
                className="history-card"
                href={`/predictions/${prediction.id}`}
                key={prediction.id}
              >
                <span className="source-pill source-pill-live">
                  置信等级 {prediction.confidence_level}
                </span>
                <h2>{matchLabel(prediction.home_team, prediction.away_team)}</h2>
                <div className="history-probabilities">
                  <span>
                    <b>主胜</b>
                    {percent(prediction.probabilities.home_win)}
                  </span>
                  <span>
                    <b>平局</b>
                    {percent(prediction.probabilities.draw)}
                  </span>
                  <span>
                    <b>客胜</b>
                    {percent(prediction.probabilities.away_win)}
                  </span>
                </div>
                {prediction.source_summary ? (
                  <p>
                    {prediction.source_summary.ingested_source_count} 个数据源 /{" "}
                    {prediction.source_summary.snapshot_count} 个快照 /{" "}
                    {prediction.source_summary.validated_fact_count} 条已验证事实
                  </p>
                ) : (
                  <p>未附加持久化数据源证据。</p>
                )}
              </a>
            ))}
          </section>
        ) : (
          <section className="prediction-panel">
            <h2>暂无已保存预测</h2>
            <p className="summary compact">
              从首页运行一次基于数据源的预测，即可创建第一条可审计记录。
            </p>
          </section>
        )
      ) : (
        <section className="prediction-panel">
          <h2>预测历史不可用</h2>
          <p className="summary compact">
            启动后端服务后才能读取已保存的比赛预测。
          </p>
        </section>
      )}
    </main>
  );
}
