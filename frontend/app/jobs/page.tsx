import { JobsDashboard, JobsPayload } from "./jobs-dashboard";

async function fetchJobs(): Promise<JobsPayload | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/jobs`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

export default async function JobsPage() {
  const jobs = await fetchJobs();

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">流水线任务</p>
        <h1>数据源自动化控制台</h1>
        <p className="summary">
          运行并审计完整操作闭环：采集已配置数据源、验证规范化事实，
          再创建带证据保存的预测记录。
        </p>
      </section>

      {jobs ? (
        <JobsDashboard initialJobs={jobs} />
      ) : (
        <section className="prediction-panel">
          <h2>任务 API 不可用</h2>
          <p className="summary compact">
            启动后端服务后才能查看或运行流水线任务。
          </p>
        </section>
      )}
    </main>
  );
}
