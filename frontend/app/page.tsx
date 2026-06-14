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
        <p className="eyebrow">深度预测方法论</p>
        <h1>世界杯预测工具</h1>
        <p className="summary">
          一个基于 Docker Compose 的网页系统，用于数据源快照、统计比赛预测、
          DeepSeek/GPT 分析报告和回测运行。
        </p>
      </section>

      <section className="status-grid" aria-label="系统健康状态">
        <article className="status-card">
          <span className={backendReady ? "signal signal-ok" : "signal"} />
          <div>
            <p className="label">后端</p>
            <h2>{statusLabel(health.status)}</h2>
          </div>
        </article>

        <article className="status-card">
          <span
            className={health.database === "ok" ? "signal signal-ok" : "signal"}
          />
          <div>
            <p className="label">PostgreSQL</p>
            <h2>{statusLabel(health.database)}</h2>
          </div>
        </article>
      </section>

      <SourceBackedPredictionWorkbench backendReady={backendReady} />
    </main>
  );
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    ok: "正常",
    degraded: "降级",
    unavailable: "不可用",
  };
  return labels[status] ?? status;
}
