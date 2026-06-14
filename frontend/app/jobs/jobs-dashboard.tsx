"use client";

import { useState } from "react";
import { teamLabel } from "../team-labels";

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

type SchedulerStatus = {
  enabled: boolean;
  running: boolean;
  job_count: number;
  job_ids: string[];
};

export type JobsPayload = {
  jobs: JobStatus[];
  recent_runs: JobRun[];
  scheduler: SchedulerStatus;
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
      throw new Error(`刷新失败，HTTP 状态码 ${response.status}`);
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
        throw new Error(message || `任务失败，HTTP 状态码 ${response.status}`);
      }
      await refreshJobs();
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "任务失败。");
    } finally {
      setRunningJobId(null);
    }
  }

  return (
    <>
      <section className="prediction-panel">
        <p className="label">调度器</p>
        <h2>
          {payload.scheduler.enabled
            ? payload.scheduler.running
              ? "后台调度器运行中"
              : "后台调度器已启用但未运行"
            : "后台调度器未启用"}
        </h2>
        <p className="summary compact">
          {payload.scheduler.enabled
            ? `${payload.scheduler.job_count} 个计划任务：${payload.scheduler.job_ids.join(", ")}`
            : "启动后端前设置 ENABLE_SCHEDULER=true，才能按目标间隔运行流水线任务。"}
        </p>
      </section>

      <section className="jobs-grid" aria-label="流水线任务">
        {payload.jobs.map((job) => (
          <article className="job-card" key={job.job_id}>
            <span className="source-pill source-pill-live">
              目标间隔 {job.interval_minutes} 分钟
            </span>
            <h2>{jobLabel(job.job_id, job.label)}</h2>
            <p>{job.job_id}</p>
            <div className="job-status-row">
              <span>
                <b>运行次数</b>
                {job.run_count}
              </span>
              <span>
                <b>最近状态</b>
                {statusLabel(job.last_run?.status ?? "idle")}
              </span>
            </div>
            {job.last_run ? (
              <p className="job-summary">{formatSummary(job.last_run.summary)}</p>
            ) : (
              <p className="job-summary">暂无运行记录。</p>
            )}
            <button
              disabled={runningJobId !== null}
              onClick={() => runJob(job.job_id)}
              type="button"
            >
              {runningJobId === job.job_id ? "运行中" : "立即运行"}
            </button>
          </article>
        ))}
      </section>

      {error ? <p className="source-ops-error">{error}</p> : null}

      <section className="source-category">
        <div className="source-category-header">
          <p className="label">最近任务运行</p>
          <span>{payload.recent_runs.length} 条记录</span>
        </div>
        {payload.recent_runs.length ? (
          <div className="evidence-grid">
            {payload.recent_runs.map((run) => (
              <article className="evidence-card" key={run.id}>
                <span className="source-pill source-pill-live">
                  {statusLabel(run.status)}
                </span>
                <h2>{run.job_id}</h2>
                <p>{formatDate(run.finished_at)}</p>
                <p>{formatSummary(run.summary)}</p>
                {run.error ? <p>{run.error}</p> : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="summary compact">
            运行一个流水线任务后会生成第一条操作记录。
          </p>
        )}
      </section>
    </>
  );
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-CN");
}

function formatSummary(summary: Record<string, unknown>) {
  const entries = Object.entries(summary);
  if (!entries.length) {
    return "无摘要。";
  }

  return entries
    .map(([key, value]) => `${summaryKeyLabel(key)}：${summaryValueLabel(key, value)}`)
    .join(" / ");
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    completed: "已完成",
    failed: "失败",
    idle: "空闲",
    running: "运行中",
    succeeded: "成功",
  };
  return labels[status] ?? status;
}

function jobLabel(jobId: string, fallback: string) {
  const labels: Record<string, string> = {
    "create-source-backed-prediction": "创建基于数据源的预测",
    "ingest-sources": "抓取已配置数据源",
    "validate-sources": "校验数据源事实",
  };
  return labels[jobId] ?? fallback;
}

function summaryKeyLabel(key: string) {
  const labels: Record<string, string> = {
    away_team: "客队",
    conflict_count: "冲突数",
    conflicting_fact_count: "冲突事实",
    fact_count: "事实数",
    failed_source_count: "失败数据源",
    home_team: "主队",
    ingested_source_count: "已抓取数据源",
    match_count: "比赛数",
    normalized_fact_count: "归一化事实",
    prediction_id: "预测 ID",
    simulation_count: "模拟次数",
    snapshot_count: "快照数",
    source_category: "数据源分类",
    source_count: "数据源数",
    validated_fact_count: "已验证事实",
  };
  return labels[key] ?? key.replaceAll("_", " ");
}

function summaryValueLabel(key: string, value: unknown) {
  if (key === "source_category" && typeof value === "string") {
    return categoryLabel(value);
  }
  if ((key === "home_team" || key === "away_team") && typeof value === "string") {
    return teamLabel(value);
  }
  return String(value);
}

function categoryLabel(category: string) {
  const labels: Record<string, string> = {
    injury: "伤停",
    news_sentiment: "新闻情绪",
    odds: "赔率",
    player: "球员数据",
    ranking: "排名",
    schedule: "赛程",
    team_form: "球队状态",
  };
  return labels[category] ?? category.replaceAll("_", " ");
}
