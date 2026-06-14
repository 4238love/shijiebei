"use client";

import { useState } from "react";

type JobRun = {
  id: string;
  job_id: string;
  status: string;
  started_at: string;
  finished_at: string;
  summary: Record<string, unknown>;
  error: string | null;
};

type JobStatus = {
  job_id: string;
  label: string;
  interval_minutes: number;
  run_count: number;
  last_run: JobRun | null;
};

export type JobsPayload = {
  jobs: JobStatus[];
  recent_runs: JobRun[];
};

type Props = {
  initialJobs: JobsPayload;
};

export function JobsDashboard({ initialJobs }: Props) {
  const [payload, setPayload] = useState(initialJobs);
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshJobs() {
    const response = await fetch("/api/jobs", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Refresh failed with HTTP ${response.status}`);
    }
    setPayload((await response.json()) as JobsPayload);
  }

  async function runJob(jobId: string) {
    setError(null);
    setRunningJobId(jobId);
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/run`, {
        method: "POST",
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Job failed with HTTP ${response.status}`);
      }
      await refreshJobs();
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Job failed.");
    } finally {
      setRunningJobId(null);
    }
  }

  return (
    <>
      <section className="jobs-grid" aria-label="Pipeline jobs">
        {payload.jobs.map((job) => (
          <article className="job-card" key={job.job_id}>
            <span className="source-pill source-pill-live">
              target interval {job.interval_minutes}m
            </span>
            <h2>{job.label}</h2>
            <p>{job.job_id}</p>
            <div className="job-status-row">
              <span>
                <b>Runs</b>
                {job.run_count}
              </span>
              <span>
                <b>Last status</b>
                {job.last_run?.status ?? "idle"}
              </span>
            </div>
            {job.last_run ? (
              <p className="job-summary">{formatSummary(job.last_run.summary)}</p>
            ) : (
              <p className="job-summary">No runs recorded yet.</p>
            )}
            <button
              disabled={runningJobId !== null}
              onClick={() => runJob(job.job_id)}
              type="button"
            >
              {runningJobId === job.job_id ? "Running" : "Run now"}
            </button>
          </article>
        ))}
      </section>

      {error ? <p className="source-ops-error">{error}</p> : null}

      <section className="source-category">
        <div className="source-category-header">
          <p className="label">Recent job runs</p>
          <span>{payload.recent_runs.length} records</span>
        </div>
        {payload.recent_runs.length ? (
          <div className="evidence-grid">
            {payload.recent_runs.map((run) => (
              <article className="evidence-card" key={run.id}>
                <span className="source-pill source-pill-live">{run.status}</span>
                <h2>{run.job_id}</h2>
                <p>{formatDate(run.finished_at)}</p>
                <p>{formatSummary(run.summary)}</p>
                {run.error ? <p>{run.error}</p> : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="summary compact">
            Run a pipeline job to create the first operational record.
          </p>
        )}
      </section>
    </>
  );
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function formatSummary(summary: Record<string, unknown>) {
  const entries = Object.entries(summary);
  if (!entries.length) {
    return "No summary.";
  }

  return entries
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`)
    .join(" / ");
}
