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
        <p className="eyebrow">Pipeline jobs</p>
        <h1>Source automation control room</h1>
        <p className="summary">
          Run and audit the operational loop: ingest configured sources,
          validate normalized facts, then create a source-backed prediction
          record with saved evidence.
        </p>
      </section>

      {jobs ? (
        <JobsDashboard initialJobs={jobs} />
      ) : (
        <section className="prediction-panel">
          <h2>Jobs API unavailable</h2>
          <p className="summary compact">
            Start the backend service to inspect or run pipeline jobs.
          </p>
        </section>
      )}
    </main>
  );
}
